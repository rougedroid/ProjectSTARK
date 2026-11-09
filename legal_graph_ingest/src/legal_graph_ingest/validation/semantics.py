"""Conservative cross-field consistency; not a substitute for legal review."""
from __future__ import annotations

OBJECTLESS = {"exists", "occurred", "terminated", "expired", "resigned", "died", "applies", "survives", "is effective", "is valid"}
COPULAS = {"is", "are", "was", "were", "means", "includes", "excludes", "defines", "equals", "constitutes", "has", "owns", "pays", "paid", "received"}
NORMATIVE = {"obligation", "prohibition", "permission", "entitlement"}

def validate_proposition(p):
    issues = []
    subj, pred, obj = p.subject.strip(), p.predicate.strip(), (p.object or "").strip()
    logic = p.logic
    if not obj and (pred.lower() in COPULAS or (logic is not None and pred.lower() not in OBJECTLESS and len(pred.split()) <= 2)):
        issues.append("incomplete triple: predicate requires an object or explicit objectless predicate")
    if logic is None:
        return issues
    kind = logic.kind
    if kind == "rule" and p.modality.value not in {"condition", "obligation", "permission", "prohibition", "entitlement"}:
        issues.append("conditional rule cannot be represented as an unconditional assertion")
    if p.modality.value == "condition" and kind in {"fact", "definition"}:
        issues.append("conditional clause cannot assert an unconditional fact/definition")
    if p.modality.value in NORMATIVE and kind == "fact":
        issues.append("normative clause cannot be an asserted fact")
    if kind == "exception" and p.modality.value != "exception":
        issues.append("exception logic requires an exception clause")
    if kind in {"fact", "norm", "definition"} and (p.conditions or p.exceptions):
        issues.append("qualified proposition cannot be an unconditional logical claim")
    if logic.conclusion:
        c = logic.conclusion
        if kind in {"fact", "definition", "norm"}:
            if (c.subject.strip(), c.predicate.strip(), c.object.strip()) != (subj, pred, obj):
                issues.append("top-level triple differs from logical conclusion")
        if kind == "rule" and (c.subject.strip(), c.predicate.strip(), c.object.strip()) != (subj, pred, obj):
            issues.append("rule conclusion differs from top-level triple")
        if kind == "norm" and c.modality not in NORMATIVE:
            issues.append("norm conclusion must carry normative modality")
        if kind == "fact" and c.modality in NORMATIVE:
            issues.append("fact conclusion cannot carry normative modality")
    return issues
