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
    ids = [p.local_id for p in result.propositions]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValidationFailure(f"duplicate local_id values: {dupes}", raw)
    return result
