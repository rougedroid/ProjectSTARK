from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RelationType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    QUALIFIES = "QUALIFIES"
    EXCEPTS_FROM = "EXCEPTS_FROM"
    REFERS_TO = "REFERS_TO"
    DUPLICATE_OF = "DUPLICATE_OF"   # identity candidate; never merges nodes or rewrites text


class Relation(BaseModel):
    """An inferred edge. Always carries evidence, method and confidence."""
    source_id: str
    target_id: str
    relation_type: RelationType
    method: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1)
    rationale: Optional[str] = None

    def to_edge_props(self) -> dict:
        return {
            "method": self.method,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "rationale": self.rationale,
        }
