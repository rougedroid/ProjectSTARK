"""Strict rule compilation from reviewed structured JSON; never guesses from prose."""
from __future__ import annotations
from collections.abc import Mapping
from .models import Pattern
from .reasoning import Rule

FACT_MODALITIES = frozenset({'statement', 'representation', 'definition'})

def _pattern(value):
    if isinstance(value, Pattern):
        return value
    if isinstance(value, (tuple, list)) and len(value) == 3 and all(isinstance(v, str) for v in value):
        return Pattern(*value)
    if isinstance(value, str):
        parts = [x.strip() for x in value.split('|')]
        if len(parts) == 3 and all(parts):
            return Pattern(*parts)
    raise ValueError('Expected [subject,predicate,object] or subject | predicate | object')

def compile_rules(raw_rules):
    """Return (rules, diagnostics); rejects malformed/unreviewed rules, never executes text."""
    rules, errors = [], []
    if not isinstance(raw_rules, list):
        return [], [{'reason': 'compiled_rules must be a list'}]
    for index, raw in enumerate(raw_rules):
        try:
            if not isinstance(raw, Mapping):
                raise ValueError('rule must be a mapping')
            if raw.get('reviewed') is not True:
                raise ValueError('rule must be explicitly reviewed')
            rid = str(raw['rule_id'])
            premises = tuple(_pattern(v) for v in raw['premises'])
            if not premises:
                raise ValueError('at least one premise required')
            conclusion = _pattern(raw['conclusion'])
            exceptions = tuple(_pattern(v) for v in raw.get('exceptions', []))
            modality = raw.get('modality', 'statement')
            if modality not in FACT_MODALITIES:
                raise ValueError('only factual rules are executable in factual inference')
            if exceptions:
                # Rules with exceptions are retained but inference blocks until resolved.
                pass
            rules.append(Rule(rid, str(raw.get('name', rid)), premises, conclusion,
                              exceptions, str(raw.get('source_id', rid)), modality))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({'rule_index': index, 'reason': str(exc)})
    return rules, errors


def compile_parser_logic(propositions):
    """Adapt approved persisted extractor IR to executable factual rules.

    Returns (rules, diagnostics). Normative conclusions are not factual rules.
    """
    from .logic_ir import load_logic
    claims, structured, issues = load_logic(propositions)
    out = []
    for item in structured:
        if item.review_status != 'approved':
            issues.append({'proposition_id': item.source_id, 'reason': 'rule not approved'})
            continue
        if item.exceptions:
            issues.append({'proposition_id': item.source_id, 'reason': 'unsupported exceptions'})
            continue
        if item.conclusion.modality not in FACT_MODALITIES:
            issues.append({'proposition_id': item.source_id, 'reason': 'normative conclusion: not a factual rule'})
            continue
        if len(item.branches) != 1:
            issues.append({'proposition_id': item.source_id, 'reason': 'unsupported disjunction'})
            continue
        premises = item.branches[0]
        if any(p.modality not in FACT_MODALITIES or p.temporal_scope or p.polarity != 'positive' for p in premises):
            issues.append({'proposition_id': item.source_id, 'reason': 'unsupported normative/temporal/negative premise'})
            continue
        out.append(Rule(item.rule_id, item.rule_id, tuple(p.pattern for p in premises), item.conclusion.pattern, (), item.source_id, item.conclusion.modality))
    return out, issues
