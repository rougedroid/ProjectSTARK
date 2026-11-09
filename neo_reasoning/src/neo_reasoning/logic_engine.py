"""Conservative fixed-point reasoning over approved structured logic, with provenance."""
from __future__ import annotations
from .logic_ir import load_logic
from .models import Pattern

FACT_MODALITIES = {'statement', 'representation', 'definition'}
NORM_MODALITIES = {'obligation', 'permission', 'prohibition', 'entitlement'}

def key(claim):
    p = claim.pattern
    return (p.subject, p.predicate, p.object, claim.modality, claim.polarity, claim.temporal_scope)

def _bindings(template, concrete, bound):
    b = dict(bound)
    for t, v in zip(template.pattern.as_tuple(), concrete.pattern.as_tuple()):
        if t.startswith('?'):
            if t in b and b[t] != v: return None
            b[t] = v
        elif t != v: return None
    if template.modality != concrete.modality or template.polarity != concrete.polarity or template.temporal_scope != concrete.temporal_scope:
        return None
    return b

def _instantiate(claim, binding):
    from .logic_ir import LogicalClaim
    p = claim.pattern
    return LogicalClaim(Pattern(*(binding.get(v, v) for v in p.as_tuple())), claim.modality, claim.polarity, claim.source_id, claim.review_status, claim.kind, claim.temporal_scope)

def infer(facts, *, max_rounds=5, max_results=1000, include_proposed=False):
    """No closed-world negation; exception-bearing rules are withheld. No writes to Neo4j."""
    claims, rules, issues = load_logic(facts)
    usable = [c for c in claims if c.review_status == 'approved' or include_proposed and c.review_status == 'proposed']
    known = {key(c): {'claim': c, 'sources': [c.source_id], 'rule_ids': [], 'depth': 0} for c in usable}
    blocked = [{'rule_id': r.rule_id, 'reason': 'not approved'} for r in rules if r.review_status != 'approved' and not include_proposed]
    blocked += [issue for issue in issues if "unsupported" in issue["reason"]]
    for rule in rules:
        if rule.review_status != 'approved' and not (include_proposed and rule.review_status == 'proposed'): continue
        if rule.exceptions:
            blocked.append({'rule_id': rule.rule_id, 'reason': 'exception applicability unresolved'})
            continue
        if any(a.modality not in FACT_MODALITIES for branch in rule.branches for a in branch):
            blocked.append({'rule_id': rule.rule_id, 'reason': 'normative premise not treated as performed fact'})
            continue
        if any(a.temporal_scope for branch in rule.branches for a in branch):
            blocked.append({'rule_id': rule.rule_id, 'reason': 'temporal premise requires time evaluation'})
            continue
    allowed = [r for r in rules if (r.review_status == 'approved' or include_proposed and r.review_status == 'proposed') and not r.exceptions and all(a.modality in FACT_MODALITIES and not a.temporal_scope for branch in r.branches for a in branch)]
    derived = {}
    for depth in range(1, max(0, min(max_rounds, 10)) + 1):
        pending = {}
        for rule in allowed:
            for branch in rule.branches:
                bindings = [({}, [], [])]
                for premise in branch:
                    next_b = []
                    for b, sources, rule_ids in bindings:
                        for rec in known.values():
                            b2 = _bindings(premise, rec['claim'], b)
                            if b2 is not None:
                                next_b.append((b2, sources + rec['sources'], rule_ids + rec['rule_ids']))
                                if len(next_b) >= max_results: break
                        if len(next_b) >= max_results: break
                    bindings = next_b
                    if not bindings: break
                for b, sources, rule_ids in bindings:
                    result = _instantiate(rule.conclusion, b)
                    if any(x.startswith('?') for x in result.pattern.as_tuple()): continue
                    k = key(result)
                    if k in known or k in pending: continue
                    pending[k] = {'claim': result, 'sources': sorted(set(sources + [rule.source_id])), 'rule_ids': list(dict.fromkeys(rule_ids + [rule.rule_id])), 'depth': depth}
                    if len(derived) + len(pending) >= max_results: break
                if len(derived) + len(pending) >= max_results: break
            if len(derived) + len(pending) >= max_results: break
        if not pending: break
        known.update(pending)
        derived.update(pending)
        if len(derived) >= max_results: break
    def serial(rec):
        c = rec['claim']
        return {'pattern': c.pattern.as_tuple(), 'modality': c.modality, 'polarity': c.polarity, 'temporal_scope': c.temporal_scope, 'sources': rec['sources'], 'rule_ids': rec['rule_ids'], 'depth': rec['depth']}
    return {'known': [serial(v) for v in known.values()], 'derived': [serial(v) for v in derived.values()], 'blocked': blocked, 'diagnostics': issues, 'rule_count': len(allowed), 'claim_count': len(usable), 'review_mode': 'including_proposed' if include_proposed else 'approved_only'}

def evaluate(result, goal: Pattern, modality='statement', temporal_scope=None):
    positive, negative = [], []
    for rec in result['known']:
        if tuple(rec['pattern']) != goal.as_tuple() or rec['modality'] != modality or rec['temporal_scope'] != temporal_scope: continue
        (positive if rec['polarity'] == 'positive' else negative).append(rec)
    status = 'conflicted' if positive and negative else 'supported' if positive else 'refuted' if negative else 'unknown'
    return {'status': status, 'positive': positive, 'negative': negative, 'goal': goal.as_tuple(), 'modality': modality, 'note': 'Support is for the stated modality, not proof of action completion.'}
