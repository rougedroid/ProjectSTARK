"""Stage 5a: parse and schema-validate raw model output. Never silently accept bad responses."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ..models.proposition import ExtractionResult


class ValidationFailure(Exception):
    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.message = message
        self.raw = raw


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_extraction(raw: str) -> ExtractionResult:
    text = _FENCE.sub("", (raw or "").strip())
    if not text:
        raise ValidationFailure("empty response", raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailure(f"not valid JSON: {exc}", raw) from exc
    if isinstance(data, list):  # tolerate a bare list of propositions
        data = {"propositions": data}
    try:
        result = ExtractionResult.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:8])
        raise ValidationFailure(f"schema violation: {details}", raw) from exc
    if any(p.logic and p.logic.review_status != "proposed" for p in result.propositions):
        raise ValidationFailure("LLM output must have proposed review status", raw)
    # A rule's antecedent is not an independently asserted fact from the same quote.
    def premise_atoms(expr):
        if expr is None: return set()
        if expr.op == "atom":
            a = expr.atom
            return {(a.subject.strip(), a.predicate.strip(), a.object.strip())}
        result_atoms = set()
        for child in expr.args:
            result_atoms.update(premise_atoms(child))
        return result_atoms
    for conditional in result.propositions:
        if not conditional.logic or conditional.logic.kind != "rule":
            continue
        antecedents = premise_atoms(conditional.logic.premise)
        for candidate in result.propositions:
            if candidate is conditional or candidate.source_quote != conditional.source_quote:
                continue
            if (candidate.subject.strip(), candidate.predicate.strip(), (candidate.object or "").strip()) in antecedents and (not candidate.logic or candidate.logic.kind == "fact"):
                raise ValidationFailure("conditional premise incorrectly asserted as unconditional fact", raw)
    ids = [p.local_id for p in result.propositions]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValidationFailure(f"duplicate local_id values: {dupes}", raw)
    return result
