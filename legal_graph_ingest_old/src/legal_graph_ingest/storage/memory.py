"""In-memory Repository: used by tests and by `--dry-run`. Mirrors Neo4jRepository semantics."""
from __future__ import annotations

from typing import Optional

from ..models.document import DocumentRecord
from ..models.mention import Mention
from ..models.proposition import Entity, Proposition
from ..models.relation import Relation
from .repository import CHECKPOINT_DONE, CHECKPOINT_QUARANTINED, ClauseBatch, Repository


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self.documents: dict[str, DocumentRecord] = {}
        self.mentions: dict[str, Mention] = {}
        self.propositions: dict[str, Proposition] = {}
        self.entities: dict[str, Entity] = {}
        self.relations: list[Relation] = []
        self.checkpoints: dict[tuple[str, str], str] = {}
        self.quarantine: dict[tuple[str, str], dict] = {}

    def init_schema(self) -> None:
        pass

    def upsert_document(self, record: DocumentRecord) -> None:
        existing = self.documents.get(record.document_id)
        if existing:
            record.ingestion_status = existing.ingestion_status
        self.documents[record.document_id] = record

    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        return self.documents.get(document_id)

    def set_status(self, document_id: str, status: str) -> None:
        self.documents[document_id].ingestion_status = status

    def clause_status(self, document_id: str, clause_key: str) -> Optional[str]:
        return self.checkpoints.get((document_id, clause_key))

    def save_clause(self, document_id: str, batch: ClauseBatch) -> None:
        for m in batch.mentions:
            self.mentions[m.mention_id] = m.model_copy(deep=True)
        for e in batch.entities:
            cur = self.entities.get(e.entity_id)
            if cur:
                cur.aliases = list(dict.fromkeys(cur.aliases + e.aliases))
            else:
                self.entities[e.entity_id] = e.model_copy(deep=True)
        for p in batch.propositions:
            cur = self.propositions.get(p.proposition_id)
            if cur:
                cur.mention_ids = list(dict.fromkeys(cur.mention_ids + p.mention_ids))
            else:
                self.propositions[p.proposition_id] = p.model_copy(deep=True)
        self.checkpoints[(document_id, batch.clause_key)] = CHECKPOINT_DONE
        self.quarantine.pop((document_id, batch.clause_key), None)

    def quarantine_clause(self, document_id: str, clause_key: str, error: str, raw: str) -> None:
        self.quarantine[(document_id, clause_key)] = {"clause_key": clause_key, "error": error, "raw_response": raw}
        self.checkpoints[(document_id, clause_key)] = CHECKPOINT_QUARANTINED

    def count_clauses(self, document_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for (doc, _), status in self.checkpoints.items():
            if doc == document_id:
                out[status] = out.get(status, 0) + 1
        return out

    def _starts(self, p: Proposition) -> int:
        return min((self.mentions[m].start_offset for m in p.mention_ids if m in self.mentions), default=0)

    def load_mentions(self, document_id: str) -> list[Mention]:
        return sorted(
            (m for m in self.mentions.values() if m.document_id == document_id),
            key=lambda m: (m.start_offset, m.end_offset),
        )

    def load_propositions(self, document_id: str) -> list[Proposition]:
        props = [p for p in self.propositions.values() if p.document_id == document_id]
        return [p.model_copy(deep=True) for p in sorted(props, key=self._starts)]

    def load_entities(self, document_id: str) -> list[Entity]:
        return sorted((e for e in self.entities.values() if e.document_id == document_id), key=lambda e: e.canonical_name)

    def load_relations(self, document_id: str) -> list[Relation]:
        ids = {p.proposition_id for p in self.propositions.values() if p.document_id == document_id}
        return [r for r in self.relations if r.source_id in ids]

    def load_quarantine(self, document_id: str) -> list[dict]:
        return [v for (doc, _), v in sorted(self.quarantine.items()) if doc == document_id]

    def save_resolution(self, document_id: str, props: list[Proposition], relations: list[Relation]) -> None:
        ids = {p.proposition_id for p in props}
        self.relations = [r for r in self.relations if r.source_id not in ids]
        self.relations.extend(r.model_copy(deep=True) for r in relations)
        for p in props:
            self.propositions[p.proposition_id].references = [r.model_copy(deep=True) for r in p.references]
