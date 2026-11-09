"""Conservative, explainable reasoning primitives. No natural-language inference."""
from __future__ import annotations
from dataclasses import dataclass
from .models import Pattern, Proposition

@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    premises: tuple[Pattern, ...]
    conclusion: Pattern
    exceptions: tuple[Pattern, ...] = ()
    source_id: str = ""
    modality: str = "statement"


def parse_pattern(text: str) -> Pattern | None:
    """Only explicit `subject | predicate | object` strings are executable."""
    pieces = [x.strip() for x in text.split('|')]
    return Pattern(*pieces) if len(pieces) == 3 and all(pieces) else None


def project_rules(facts: list[Proposition]) -> tuple[list[Rule], list[dict]]:
    """Project ONLY fully structured conditional propositions; report non-executable clauses."""
    rules, skipped = [], []
    for p in facts:
        if p.logic_json or not p.conditions:
            continue
        premises = [parse_pattern(s) for s in p.conditions]
        exceptions = [parse_pattern(s) for s in p.exceptions]
        if (p.modality in {'condition', 'statement', 'obligation', 'prohibition', 'permission', 'entitlement'}
            and p.polarity == 'positive' and all(premises) and all(exceptions)):
            rules.append(Rule(p.proposition_id, p.normalized_text or p.proposition_id,
                              tuple(premises), p.pattern(), tuple(exceptions), p.proposition_id, p.modality))
        else:
            skipped.append({'proposition_id': p.proposition_id, 'reason': 'unstructured conditions/exceptions or unsupported modality/polarity'})
    return rules, skipped


def match_pattern(template: Pattern, concrete: Pattern) -> dict[str, str] | None:
    binding = {}
    for a, b in zip(template.as_tuple(), concrete.as_tuple()):
        if a.startswith('?'):
            if a in binding and binding[a] != b: return None
            binding[a] = b
        elif a != b: return None
    return binding


def substitute(pattern: Pattern, binding: dict[str, str]) -> Pattern:
    return Pattern(*(binding.get(v, v) for v in pattern.as_tuple()))


def is_ground(pattern: Pattern) -> bool:
    return all(not t.startswith('?') for t in pattern.as_tuple())


def is_unconditional(p: Proposition) -> bool:
    return (not p.conditions and not p.exceptions and not p.temporal_scope
            and p.modality in {'statement', 'representation', 'definition'})


def classify(p: Proposition) -> str:
    """Negative polarity is not negation of an obligation/permission."""
    if p.logic_json:
        from .logic_ir import parse_logic
        claim, rule, issue = parse_logic(p.logic_json, p.proposition_id)
        if issue or rule or not claim or claim.review_status != "approved": return "qualified"
        if claim.kind != "fact" or claim.modality not in {"statement", "representation"}: return "qualified"
        if claim.pattern != p.pattern() or not p.object.strip(): return "qualified"
    else:
        return "qualified"  # legacy extractions require explicit review
    if not is_unconditional(p): return 'qualified'
    return 'positive' if p.polarity == 'positive' else 'negative'


def collect(graph, workspace, limit=5000):
    return graph.facts(limit=limit, document_ids=workspace.document_ids or None)


def explicit_edges(graph, fact_ids: set[str], relation: str):
    result = []
    for pid in sorted(fact_ids):
        result.extend(graph.edges(pid, relation=relation, direction='out'))
    return [e for e in result if e.source_id in fact_ids and e.target_id in fact_ids]


def load_rules(facts, workspace):
    """Load explicit structured rules plus optional reviewed rules in workspace metadata."""
    from .compiler import compile_rules, compile_parser_logic
    rules, skipped = project_rules(facts)
    structured, issues = compile_parser_logic(facts)
    rules += structured
    skipped += issues
    extra, errors = compile_rules(workspace.metadata.get('compiled_rules', []))
    return rules + extra, skipped + errors

def applicable_rule(rule: Rule, workspace) -> bool:
    """Only factual rules are used to derive factual triples. Normative rules are separate."""
    return rule.modality in {'statement', 'representation', 'definition'}
