"""Operators over new extractor logic_json; intentionally independent from extractor package."""
from .base import ReasoningOperator
from ..models import ReasoningAction
from ..logic_engine import infer, evaluate

def _actions(op, graph, workspace, description):
    if workspace.goal is None: return []
    return [ReasoningAction(op.name, workspace.goal, description, {})]

def _run(graph, workspace, action):
    facts = graph.facts(limit=min(int(action.parameters.get('max_facts', 5000)), 20000), document_ids=workspace.document_ids or None)
    return infer(facts, max_rounds=int(action.parameters.get('max_rounds', 5)), max_results=int(action.parameters.get('max_results', 1000)), include_proposed=bool(action.parameters.get('include_proposed', workspace.metadata.get('include_proposed', False))))

class StructuredForwardInference(ReasoningOperator):
    name = 'structured_forward_inference'
    def available_actions(self, graph, workspace): return _actions(self, graph, workspace, 'Derive claims from approved logical IR')
    def execute(self, graph, workspace, action):
        data = _run(graph, workspace, action)
        result = {k:v for k,v in data.items() if k != 'known'}
        workspace.evidence.extend({'kind': 'structured_inference', **v} for v in result['derived'])
        workspace.record(self.name, action.description, result)
        return result

class StructuredHypothesisTesting(ReasoningOperator):
    name = 'structured_hypothesis_testing'
    def available_actions(self, graph, workspace): return _actions(self, graph, workspace, 'Test a modality-specific claim against approved logic')
    def execute(self, graph, workspace, action):
        data = _run(graph, workspace, action)
        result = evaluate(data, action.goal or workspace.goal, modality=action.parameters.get('modality', workspace.metadata.get('modality', 'statement')), temporal_scope=action.parameters.get('temporal_scope', workspace.metadata.get('temporal_scope')))
        result.update({'rule_count': data['rule_count'], 'blocked': data['blocked'], 'diagnostics': data['diagnostics'], 'review_mode': data['review_mode']})
        workspace.record(self.name, action.description, result)
        return result

class StructuredBackwardChaining(ReasoningOperator):
    name = 'structured_backward_chaining'
    def available_actions(self, graph, workspace): return _actions(self, graph, workspace, 'Find provenance of a derived logical goal')
    def execute(self, graph, workspace, action):
        data = _run(graph, workspace, action)
        result = evaluate(data, action.goal or workspace.goal, modality=action.parameters.get('modality', workspace.metadata.get('modality', 'statement')))
        result['proofs'] = result['positive'] + result['negative']
        result['method'] = 'forward-closure proof provenance (not recursive goal-directed search)'
        result['blocked'] = data['blocked']
        workspace.record(self.name, action.description, result)
        return result

class NormativeAnalysis(ReasoningOperator):
    name = 'normative_analysis'
    def available_actions(self, graph, workspace): return _actions(self, graph, workspace, 'Inspect obligations, permissions, prohibitions without conflating facts')
    def execute(self, graph, workspace, action):
        data = _run(graph, workspace, action)
        goal = action.goal or workspace.goal
        claims = [c for c in data['known'] if tuple(c['pattern']) == goal.as_tuple() and c['modality'] in ('obligation','permission','prohibition','entitlement')]
        result = {'norms': claims, 'count': len(claims), 'note': 'Normative claims do not prove compliance or legal validity.'}
        workspace.record(self.name, action.description, result)
        return result
