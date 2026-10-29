"""Typed graph records. Optional Neo4j properties are represented as None."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import json

@dataclass(frozen=True)
class Pattern:
    subject: str
    predicate: str
    object: str
    def as_tuple(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)

@dataclass(frozen=True)
class Document:
    document_id: str
    filename: str = ""
    sha256: str = ""
    page_count: int = 0
    ingestion_status: str = ""

@dataclass(frozen=True)
class Mention:
    mention_id: str
    document_id: str
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    clause_number: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    source_text: str = ""

@dataclass(frozen=True)
class Entity:
    entity_id: str
    document_id: str
    canonical_name: str
    entity_type: str = "other"
    aliases: tuple[str, ...] = ()

@dataclass(frozen=True)
class Reference:
    surface_text: str
    kind: str
    candidate_ids: tuple[str, ...] = ()
    resolved_id: str | None = None
    method: str | None = None
    confidence: float | None = None

@dataclass(frozen=True)
class Proposition:
    proposition_id: str
    document_id: str
    clause_key: str = ""
    local_id: str = ""
    subject: str = ""
    predicate: str = ""
    object: str = ""
    normalized_text: str = ""
    modality: str = "statement"
    polarity: str = "positive"
    conditions: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    temporal_scope: str | None = None
    attribution: str = "contract"
    extraction_confidence: float | None = None
    source_quote: str = ""
    references: tuple[Reference, ...] = ()
    def pattern(self) -> Pattern:
        return Pattern(self.subject, self.predicate, self.object)
    @property
    def truth(self) -> bool:
        """Compatibility only: negative polarity is NOT necessarily logical falsity."""
        return self.polarity == "positive"
    @classmethod
    def from_neo4j(cls, props: dict[str, Any]) -> Proposition:
        d = dict(props)
        raw = d.pop("references_json", "[]") or "[]"
        try:
            refs = json.loads(raw)
        except (ValueError, TypeError):
            refs = []
        allowed = cls.__dataclass_fields__
        d = {k: v for k, v in d.items() if k in allowed and k != "references"}
        for k in ("conditions", "exceptions"):
            d[k] = tuple(d.get(k) or ())
        d["references"] = tuple(Reference(**{k: v for k, v in r.items() if k in Reference.__dataclass_fields__}) for r in refs if isinstance(r, dict))
        return cls(**d)

@dataclass(frozen=True)
class SemanticEdge:
    source_id: str
    target_id: str
    relation: str
    method: str = ""
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    rationale: str = ""

@dataclass(frozen=True)
class Evidence:
    proposition: Proposition
    mentions: tuple[Mention, ...] = ()
    subject_entities: tuple[Entity, ...] = ()
    object_entities: tuple[Entity, ...] = ()

@dataclass(frozen=True)
class ReasoningAction:
    operator: str
    goal: Pattern | None
    description: str
    features: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
