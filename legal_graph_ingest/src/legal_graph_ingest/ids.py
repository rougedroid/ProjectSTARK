"""Deterministic identifiers, so re-running the pipeline never duplicates records."""
from __future__ import annotations

import hashlib
import re


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:16]}"


def normalize_key(text: str) -> str:
    """Casefolded, punctuation-free key used for identity/dedup comparisons."""
    return re.sub(r"\W+", " ", text.casefold()).strip()
