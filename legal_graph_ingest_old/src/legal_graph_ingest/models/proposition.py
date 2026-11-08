from __future__ import annotations

import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Modality(str, Enum):
    OBLIGATION = "obligation"          # must / shall
    PROHIBITION = "prohibition"        # must not / shall not
    PERMISSION = "permission"          # may
    ENTITLEMENT = "entitlement"        # is entitled to / has the right to
    EXCEPTION = "exception"            # does not apply where ...
    CONDITION = "condition"            # if / provided that
    DEFINITION = "definition"          # "X" means ...
    REPRESENTATION = "representation"  # warrants / represents
    STATEMENT = "statement"            # plain statement of fact


class Polarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ReferenceKind(str, Enum):
    PRONOUN = "pronoun"
    ANAPHORIC_PHRASE = "anaphoric_phrase"   # "the foregoing obligation"
    DEFINED_TERM = "defined_term"
    CROSS_REFERENCE = "cross_reference"     # "as set out in clause 4"


def _none_to_list(cls: Any, v: Any) -> Any:
    return [] if v is None else v


class Reference(BaseModel):
    """An unresolved (or later resolved) pointer from a proposition to an antecedent."""
    surface_text: str
    kind: ReferenceKind = ReferenceKind.ANAPHORIC_PHRASE
    candidate_ids: list[str] = Field(default_factory=list)
    resolved_id: Optional[str] = None
    method: Optional[str] = None
    confidence: Optional[float] = None

    @field_validator("candidate_ids", mode="before")
    @classmethod
    def _cands(cls, v: Any) -> Any:
        return [] if v is None else v

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class ExtractedProposition(BaseModel):
    """Schema the LLM must return for each proposition."""
    local_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: Optional[str] = None
    normalized_text: str = Field(min_length=1)
    modality: Modality
    polarity: Polarity = Polarity.POSITIVE
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    temporal_scope: Optional[str] = None
    attribution: str = "contract"
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_quote: str = Field(min_length=1)
    references: list[Reference] = Field(default_factory=list)

    @field_validator("conditions", "exceptions", "references", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> Any:
        return [] if v is None else v

    @field_validator("modality", "polarity", mode="before")
    @classmethod
    def _lower(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class ExtractionResult(BaseModel):
    propositions: list[ExtractedProposition] = Field(default_factory=list)

    @field_validator("propositions", mode="before")
    @classmethod
    def _props(cls, v: Any) -> Any:
        return [] if v is None else v


class Proposition(ExtractedProposition):
    """A validated proposition with a stable id, as persisted in the graph."""
    proposition_id: str
    document_id: str
    clause_key: str
    mention_ids: list[str] = Field(default_factory=list)
    subject_entity_id: Optional[str] = None
    object_entity_id: Optional[str] = None

    def to_node_props(self) -> dict:
        return {
            "proposition_id": self.proposition_id,
            "document_id": self.document_id,
            "clause_key": self.clause_key,
            "local_id": self.local_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "normalized_text": self.normalized_text,
            "modality": self.modality.value,
            "polarity": self.polarity.value,
            "conditions": list(self.conditions),
            "exceptions": list(self.exceptions),
            "temporal_scope": self.temporal_scope,
            "attribution": self.attribution,
            "extraction_confidence": self.extraction_confidence,
            "source_quote": self.source_quote,
            "references_json": json.dumps([r.model_dump(mode="json") for r in self.references]),
        }

    @classmethod
    def from_node_props(
        cls,
        p: dict,
        mention_ids: list[str] | None = None,
        subject_entity_id: str | None = None,
        object_entity_id: str | None = None,
    ) -> "Proposition":
        refs = json.loads(p.get("references_json") or "[]")
        return cls(
            proposition_id=p["proposition_id"],
            document_id=p["document_id"],
            clause_key=p.get("clause_key", ""),
            local_id=p.get("local_id") or p["proposition_id"],
            subject=p["subject"],
            predicate=p["predicate"],
            object=p.get("object"),
            normalized_text=p["normalized_text"],
            modality=p["modality"],
            polarity=p.get("polarity", "positive"),
            conditions=p.get("conditions") or [],
            exceptions=p.get("exceptions") or [],
            temporal_scope=p.get("temporal_scope"),
            attribution=p.get("attribution") or "contract",
            extraction_confidence=p.get("extraction_confidence") or 0.5,
            source_quote=p["source_quote"],
            references=refs,
            mention_ids=mention_ids or [],
            subject_entity_id=subject_entity_id,
            object_entity_id=object_entity_id,
        )


class Entity(BaseModel):
    entity_id: str
    document_id: str
    canonical_name: str
    entity_type: str = "other"
    aliases: list[str] = Field(default_factory=list)

    def to_node_props(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_node_props(cls, p: dict) -> "Entity":
        return cls(
            entity_id=p["entity_id"],
            document_id=p.get("document_id", ""),
            canonical_name=p.get("canonical_name", ""),
            entity_type=p.get("entity_type", "other"),
            aliases=p.get("aliases") or [],
        )
