"""Implemented, conservative operators over document propositions.

Statuses are evidence classifications, not legal judgments. In particular,
SUPPORTS edges are corroborative annotations, not formal implication.
"""
from __future__ import annotations
from .base import ReasoningOperator
from ..models import ReasoningAction, Pattern
from ..reasoning import (collect, classify, project_rules, match_pattern, substitute,
                         is_ground, explicit_edges)


def _result(op, workspace, action, data):
    workspace.record(op.name, action.description, data)
    return data


def _action(op, graph, workspace, description):
    if workspace.goal is None: return []
    return [ReasoningAction(op.name, workspace.goal, description, {'fact_count': float(graph.count_facts(workspace.document_ids or None))})]


def _evidence(facts, goal):
    pos, neg, qualified = [], [], []
    for p in facts:
        if match_pattern(goal, p.pattern()) is None: continue
        kind = classify(p)
        (pos if kind == 'positive' else neg if kind == 'negative' else qualified).append(p.proposition_id)
    return sorted(pos), sorted(neg), sorted(qualified)


class OperatorTemplate(ReasoningOperator):
    name = 'operator_template'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Custom operator')
    def execute(self, graph, workspace, action):
        raise NotImplementedError('Implement your own operator')


class HypothesisTesting(ReasoningOperator):
    name = 'hypothesis_testing'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Classify direct, unconditional evidence for goal')
    def execute(self, graph, workspace, action):
        goal = action.goal or workspace.goal
        if goal is None: raise ValueError('Goal required')
        facts = collect(graph, workspace)
        pos, neg, qualified = _evidence(facts, goal)
        status = 'conflicted' if pos and neg else 'supported' if pos else 'refuted' if neg else 'unknown'
        result = {'status': status, 'supporting_fact_ids': pos, 'contradicting_fact_ids': neg,
                  'qualified_fact_ids': qualified, 'scope': 'direct_unconditional_evidence',
                  'note': 'Unknown does not mean false; qualified norms are not truth-valued facts.'}
        workspace.candidate_hypotheses.append({'goal': goal.as_tuple(), **result})
        if status in {'unknown', 'conflicted'}:
            workspace.unresolved_questions.append(f'{status}: {goal.as_tuple()}')
        return _result(self, workspace, action, result)


class CounterexampleRetrieval(ReasoningOperator):
    name = 'counterexample_retrieval'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Find explicit exceptions and opposing evidence')
    def execute(self, graph, workspace, action):
        goal = action.goal or workspace.goal
        if goal is None: raise ValueError('Goal required')
        facts = collect(graph, workspace)
        ids = {p.proposition_id for p in facts}
        _, negative, qualified = _evidence(facts, goal)
        rules, skipped = project_rules(facts)
        counterexamples = [{'kind': 'negative_evidence', 'proposition_id': pid} for pid in negative]
        counterexamples += [{'kind': 'qualified_proposition', 'proposition_id': pid} for pid in qualified]
        for rule in rules:
            if match_pattern(goal, rule.conclusion) is not None:
                for exc in rule.exceptions:
                    for p in facts:
                        if classify(p) == 'positive' and match_pattern(exc, p.pattern()) is not None:
                            counterexamples.append({'kind': 'triggered_exception', 'rule_id': rule.rule_id, 'fact_id': p.proposition_id})
        for e in explicit_edges(graph, ids, 'CONTRADICTS'):
            if e.source_id in ids and e.target_id in ids:
                if any(p.proposition_id in (e.source_id, e.target_id) and match_pattern(goal, p.pattern()) is not None for p in facts):
                    counterexamples.append({'kind': 'contradiction_annotation', 'source_id': e.source_id, 'target_id': e.target_id})
        return _result(self, workspace, action, {'counterexamples': counterexamples, 'count': len(counterexamples), 'unprojected_rules': skipped})


class ForwardInference(ReasoningOperator):
    name = 'forward_inference'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Apply fully structured conditional rules')
    def execute(self, graph, workspace, action):
        facts = collect(graph, workspace)
        rules, skipped = project_rules(facts)
        known = {p.pattern().as_tuple(): {'sources': [p.proposition_id], 'depth': 0} for p in facts if classify(p) == 'positive'}
        derived = {}
        max_depth = max(0, min(int(action.parameters.get('max_depth', 3)), 10))
        max_derivations = max(1, min(int(action.parameters.get('max_derivations', 1000)), 10000))
        for depth in range(1, max_depth + 1):
            pending = {}
            for rule in rules:
                bindings = [({}, [])]
                for premise in rule.premises:
                    next_bindings = []
                    for bound, sources in bindings:
                        for triple, record in list(known.items()):
                            b = match_pattern(substitute(premise, bound), Pattern(*triple))
                            if b is not None and all(k not in bound or bound[k] == v for k, v in b.items()):
                                next_bindings.append(({**bound, **b}, sources + record['sources']))
                    bindings = next_bindings[:max_derivations]
                    if not bindings: break
                for binding, sources in bindings:
                    conclusion = substitute(rule.conclusion, binding)
                    if not is_ground(conclusion) or conclusion.as_tuple() in known: continue
                    # Open-world exception policy: unresolved exceptions block the inference.
                    if rule.exceptions:
                        continue
                    pending[conclusion.as_tuple()] = {'sources': sorted(set(sources + [rule.source_id])), 'rule_id': rule.rule_id, 'depth': depth}
                    if len(derived) + len(pending) >= max_derivations: break
                if len(derived) + len(pending) >= max_derivations: break
            if not pending: break
            known.update(pending)
            derived.update(pending)
            if len(derived) >= max_derivations: break
        result = {'derived': [{'pattern': k, **v} for k, v in derived.items()], 'count': len(derived),
                  'unprojected_rules': skipped, 'note': 'Rules with exceptions are withheld until exception handling can establish non-applicability; derived facts remain workspace-only.'}
        workspace.evidence.extend({'kind': 'inference', **d} for d in result['derived'])
        return _result(self, workspace, action, result)


class BackwardChaining(ReasoningOperator):
    name = 'backward_chaining'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Find grounded proof paths and unresolved premises')
    def execute(self, graph, workspace, action):
        goal = action.goal or workspace.goal
        if goal is None: raise ValueError('Goal required')
        facts = collect(graph, workspace)
        rules, skipped = project_rules(facts)
        max_depth = max(0, min(int(action.parameters.get('max_depth', 4)), 10))
        def prove(target, depth, visiting):
            key = target.as_tuple()
            if key in visiting: return {'status': 'cycle', 'goal': key}
            pos, neg, qualified = _evidence(facts, target)
            if pos and neg: return {'status': 'conflicted', 'goal': key, 'positive': pos, 'negative': neg}
            if pos: return {'status': 'supported', 'goal': key, 'fact_ids': pos}
            if depth == 0: return {'status': 'unknown', 'goal': key, 'qualified': qualified}
            attempts = []
            for rule in rules:
                binding = match_pattern(rule.conclusion, target)
                if binding is None: continue
                if rule.exceptions:
                    attempts.append({'rule_id': rule.rule_id, 'status': 'blocked_exception_uncertainty'})
                    continue
                premises = [prove(substitute(p, binding), depth - 1, visiting | {key}) for p in rule.premises]
                if premises and all(p['status'] == 'supported' for p in premises):
                    return {'status': 'supported', 'goal': key, 'rule_id': rule.rule_id, 'premises': premises}
                attempts.append({'rule_id': rule.rule_id, 'status': 'unproven', 'premises': premises})
            return {'status': 'refuted' if neg else 'unknown', 'goal': key, 'negative': neg, 'attempts': attempts, 'qualified': qualified}
        proof = prove(goal, max_depth, set())
        if proof['status'] != 'supported': workspace.unresolved_questions.append(f'Unproven goal: {goal.as_tuple()}')
        return _result(self, workspace, action, {'status': proof['status'], 'proof': proof, 'unprojected_rules': skipped})


class RelationComposition(ReasoningOperator):
    name = 'relation_composition'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Traverse explicit proposition relationships without inventing entailments')
    def execute(self, graph, workspace, action):
        goal = action.goal or workspace.goal
        facts = collect(graph, workspace)
        by_id = {p.proposition_id: p for p in facts}
        seeds = [p.proposition_id for p in facts if goal and match_pattern(goal, p.pattern()) is not None]
        max_depth = max(0, min(int(action.parameters.get('max_depth', 2)), 8))
        max_nodes = max(1, min(int(action.parameters.get('max_nodes', 500)), 5000))
        frontier, seen, paths = [(s, [s]) for s in seeds[:max_nodes]], set(seeds[:max_nodes]), []
        for _ in range(max_depth):
            nxt = []
            for node, path in frontier:
                for edge in graph.edges(node, direction='out', limit=max_nodes):
                    if edge.target_id not in by_id: continue
                    paths.append({'path': path + [edge.target_id], 'relation': edge.relation, 'method': edge.method, 'confidence': edge.confidence})
                    if edge.target_id not in seen and len(seen) < max_nodes:
                        seen.add(edge.target_id)
                        nxt.append((edge.target_id, path + [edge.target_id]))
            frontier = nxt
            if not frontier: break
        return _result(self, workspace, action, {'seeds': seeds, 'paths': paths, 'visited_ids': sorted(seen), 'note': 'Paths are annotations, not transitive logical proofs.'})


class PlanFeasibility(ReasoningOperator):
    name = 'plan_feasibility'
    def available_actions(self, graph, workspace): return _action(self, graph, workspace, 'Assess explicit plan preconditions and conflicts')
    def execute(self, graph, workspace, action):
        plan = action.parameters.get('plan') or workspace.metadata.get('plan')
        if not isinstance(plan, list) or not all(isinstance(s, dict) for s in plan):
            return _result(self, workspace, action, {'status': 'insufficient_plan', 'steps': [], 'note': 'Provide plan=[{"name":..., "requires":[[subject,predicate,object], ...]}]'})
        facts = collect(graph, workspace)
        steps = []
        for step in plan:
            checks = []
            for raw in step.get('requires', []):
                if not isinstance(raw, (list, tuple)) or len(raw) != 3 or not all(isinstance(x, str) for x in raw):
                    raise ValueError('Each plan requirement must be a three-string pattern')
                pos, neg, qualified = _evidence(facts, Pattern(*raw))
                status = 'conflicted' if pos and neg else 'supported' if pos else 'refuted' if neg else 'unknown'
                checks.append({'requirement': raw, 'status': status, 'supporting_ids': pos, 'opposing_ids': neg, 'qualified_ids': qualified})
            steps.append({'name': step.get('name', ''), 'checks': checks, 'status': 'blocked' if any(c['status'] in ('refuted', 'conflicted') for c in checks) else 'unverified' if any(c['status'] == 'unknown' for c in checks) or not checks else 'preconditions_supported'})
        status = 'blocked' if any(s['status'] == 'blocked' for s in steps) else 'unverified' if any(s['status'] == 'unverified' for s in steps) or not steps else 'preconditions_supported'
        return _result(self, workspace, action, {'status': status, 'steps': steps, 'note': 'Supported preconditions do not establish executable or legally permitted plans.'})
