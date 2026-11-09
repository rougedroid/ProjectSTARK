"""Standalone interpretation of legal_graph_ingest.logic.schema, without depending on extractor."""
from __future__ import annotations
import json
from dataclasses import dataclass
from .models import Pattern

@dataclass(frozen=True)
class LogicalClaim:
    pattern: Pattern
    modality: str
    polarity: str
    source_id: str
    review_status: str
    kind: str
    temporal_scope: str | None = None

@dataclass(frozen=True)
class LogicalRule:
    rule_id: str
    source_id: str
    branches: tuple[tuple[LogicalClaim, ...], ...]  # DNF: OR of AND branches
    conclusion: LogicalClaim
    exceptions: tuple[dict, ...]
    review_status: str


def parse_logic(raw, source_id: str):
    """Return (claim, rule, issue). Only schema-shaped JSON is accepted."""
    if not raw: return None, None, None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict): raise ValueError('logic must be object')
        kind = data['kind']
        review = data.get('review_status', 'proposed')
        if review not in ('approved', 'proposed', 'rejected'): raise ValueError('invalid review_status')
        if kind == 'unresolved': return None, None, 'unresolved: ' + str(data.get('unresolved_reason', 'unspecified'))
        if kind == 'exception': return None, None, 'standalone exception requires linkage'
        def atom(value):
            if not isinstance(value, dict): raise ValueError('atom must be object')
            subject, predicate = value['subject'], value['predicate']
            if not isinstance(subject, str) or not subject.strip() or not isinstance(predicate, str) or not predicate.strip():
                raise ValueError('empty subject/predicate')
            obj = value.get('object', '')
            if not isinstance(obj, str): raise ValueError('object must be string')
            polarity = value.get('polarity', 'positive')
            modality = value.get('modality', 'statement')
            if polarity not in ('positive', 'negative'): raise ValueError('invalid polarity')
            if modality not in ('statement','representation','definition','obligation','prohibition','permission','entitlement'):
                raise ValueError('invalid modality')
            return LogicalClaim(Pattern(subject, predicate, obj), modality, polarity, source_id, review, kind, value.get('temporal_scope'))
        if kind in ('fact', 'norm', 'definition'):
            claim = atom(data['conclusion'])
            if data.get('premise') or data.get('exceptions'):
                return None, None, 'qualified non-rule cannot be treated as unconditional'
            return claim, None, None
        if kind != 'rule': raise ValueError('unknown kind')
        conclusion = atom(data['conclusion'])
        def dnf(expr):
            if not isinstance(expr, dict): raise ValueError('expression must be object')
            op = expr.get('op')
            if op == 'atom':
                if expr.get('args'): raise ValueError('atom cannot have args')
                return ((atom(expr['atom']),),)
            args = expr.get('args', [])
            if op == 'or': raise ValueError('unsupported disjunction: review or expand explicitly')
            if op == 'and' and len(args) >= 2:
                pieces = [dnf(a) for a in args]
                branches = ((),)
                for group in pieces:
                    branches = tuple(b + c for b in branches for c in group)
                    if len(branches) > 64: raise ValueError('expression expansion exceeds 64 branches')
                return branches
            if op == 'not':
                raise ValueError('NOT requires explicit negation semantics; not compiled')
            raise ValueError('malformed expression')
        branches = dnf(data['premise'])
        if not branches: raise ValueError('empty rule')
        if any(a.temporal_scope for branch in branches for a in branch):
            return None, None, 'unsupported temporal premise: rule withheld'
        exceptions = data.get('exceptions', [])
        if exceptions: return None, None, 'unsupported exceptions: rule withheld'
        if conclusion.temporal_scope: return None, None, 'unsupported temporal conclusion: rule withheld'
        if not isinstance(exceptions, list): raise ValueError('exceptions must be list')
        return None, LogicalRule('logic:' + source_id, source_id, branches, conclusion, tuple(exceptions), review), None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, None, str(exc)


def load_logic(facts):
    claims, rules, issues = [], [], []
    for fact in facts:
        claim, rule, issue = parse_logic(fact.logic_json, fact.proposition_id)
        if claim: claims.append(claim)
        if rule: rules.append(rule)
        if issue: issues.append({'proposition_id': fact.proposition_id, 'reason': issue})
    return claims, rules, issues
