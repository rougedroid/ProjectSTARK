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
