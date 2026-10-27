from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Mention(BaseModel):
    """A specific passage in the document: the provenance record."""
    mention_id: str
    document_id: str
    page_start: int
    page_end: int
    section: Optional[str] = None
    clause_number: Optional[str] = None
    start_offset: int
    end_offset: int
    source_text: str

    def to_node_props(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_node_props(cls, p: dict) -> "Mention":
        return cls(**{k: p.get(k) for k in cls.model_fields if k in p})
