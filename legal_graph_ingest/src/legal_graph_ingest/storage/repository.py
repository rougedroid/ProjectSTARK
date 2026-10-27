"""Stage 6: persistence. Python validates; the repository stores; Neo4j holds the graph.

All writes use deterministic ids + MERGE, so re-running never duplicates records. A clause's
mentions, propositions, entities and its checkpoint are written in ONE transaction, so a crash
can never leave a half-persisted clause that is marked done.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..ids import stable_id
from ..models.document import DocumentRecord
from ..models.mention import Mention
from ..models.proposition import Entity, Proposition
from ..models.relation import Relation, RelationType
from .constraints import SCHEMA_STATEMENTS
from .neo4j_client import Neo4jClient

SEMANTIC_TYPES = [t.value for t in RelationType]
CHECKPOINT_DONE = "done"
CHECKPOINT_QUARANTINED = "quarantined"


@dataclass
class ClauseBatch:
    clause_key: str
    mentions: list[Mention] = field(default_factory=list)
    propositions: list[Proposition] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)


class Repository(ABC):
    # -- schema / document ------------------------------------------------------------
    @abstractmethod
    def init_schema(self) -> None: ...
    @abstractmethod
    def upsert_document(self, record: DocumentRecord) -> None: ...
    @abstractmethod
    def get_document(self, document_id: str) -> Optional[DocumentRecord]: ...
    @abstractmethod
    def set_status(self, document_id: str, status: str) -> None: ...

    # -- extraction stage -------------------------------------------------------------
    @abstractmethod
    def clause_status(self, document_id: str, clause_key: str) -> Optional[str]: ...
    @abstractmethod
    def save_clause(self, document_id: str, batch: ClauseBatch) -> None: ...
    @abstractmethod
    def quarantine_clause(self, document_id: str, clause_key: str, error: str, raw: str) -> None: ...
    @abstractmethod
    def count_clauses(self, document_id: str) -> dict[str, int]: ...

    # -- reads --------------------------------------------------------------------------
    @abstractmethod
    def load_mentions(self, document_id: str) -> list[Mention]: ...
    @abstractmethod
    def load_propositions(self, document_id: str) -> list[Proposition]: ...
    @abstractmethod
    def load_entities(self, document_id: str) -> list[Entity]: ...
    @abstractmethod
    def load_relations(self, document_id: str) -> list[Relation]: ...
    @abstractmethod
    def load_quarantine(self, document_id: str) -> list[dict]: ...

    # -- resolution stage -------------------------------------------------------------
    @abstractmethod
    def save_resolution(self, document_id: str, props: list[Proposition], relations: list[Relation]) -> None:
        """Replace all inferred relations of the document and update proposition references."""


# ======================================================================================
# Neo4j implementation
# ======================================================================================
_Q_MENTIONS = """
MATCH (d:Document {document_id: $doc})
UNWIND $rows AS row
MERGE (m:Mention {mention_id: row.mention_id})
SET m += row
MERGE (d)-[:CONTAINS]->(m)
"""

_Q_PROPOSITIONS = """
UNWIND $rows AS row
MERGE (p:Proposition {proposition_id: row.props.proposition_id})
SET p += row.props
WITH p, row
MATCH (m:Mention {mention_id: row.mention_id})
MERGE (m)-[:EXPRESSES]->(p)
"""

_Q_ENTITIES = """
UNWIND $rows AS row
MERGE (e:Entity {entity_id: row.entity_id})
ON CREATE SET e.document_id = row.document_id, e.canonical_name = row.canonical_name,
              e.entity_type = row.entity_type, e.aliases = row.aliases
ON MATCH SET e.aliases = reduce(acc = coalesce(e.aliases, []), a IN row.aliases |
                                CASE WHEN a IN acc THEN acc ELSE acc + a END)
"""

_Q_SUBJECT_LINKS = """
UNWIND $rows AS row
MATCH (p:Proposition {proposition_id: row.pid}), (e:Entity {entity_id: row.eid})
MERGE (p)-[:SUBJECT_ENTITY]->(e)
"""

_Q_OBJECT_LINKS = _Q_SUBJECT_LINKS.replace("SUBJECT_ENTITY", "OBJECT_ENTITY")

_Q_CHECKPOINT = """
MATCH (d:Document {document_id: $doc})
MERGE (c:Checkpoint {key: $key})
SET c.document_id = $doc, c.clause_key = $clause, c.status = $status, c.updated_at = datetime()
MERGE (d)-[:HAS_CHECKPOINT]->(c)
"""

_Q_CLEAR_QUARANTINE = "MATCH (q:Quarantine {quarantine_id: $qid}) DETACH DELETE q"

_Q_QUARANTINE = """
MATCH (d:Document {document_id: $doc})
MERGE (q:Quarantine {quarantine_id: $qid})
SET q.document_id = $doc, q.clause_key = $clause, q.error = $error, q.raw_response = $raw,
    q.created_at = datetime()
MERGE (d)-[:HAS_QUARANTINE]->(q)
"""


class Neo4jRepository(Repository):
    def __init__(self, client: Neo4jClient):
        self.client = client

    # -- schema / document ------------------------------------------------------------
    def init_schema(self) -> None:
        for stmt in SCHEMA_STATEMENTS:
            self.client.execute(stmt)

    def upsert_document(self, record: DocumentRecord) -> None:
        existing = self.get_document(record.document_id)
        props = record.to_node_props()
        if existing:  # never reset status on re-run
            props["ingestion_status"] = existing.ingestion_status
        self.client.execute(
            "MERGE (d:Document {document_id: $id}) SET d += $props", id=record.document_id, props=props
        )

    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        rows = self.client.read("MATCH (d:Document {document_id: $id}) RETURN d", id=document_id)
        return DocumentRecord.from_node_props(rows[0]["d"]) if rows else None

    def set_status(self, document_id: str, status: str) -> None:
        self.client.execute(
            "MATCH (d:Document {document_id: $id}) SET d.ingestion_status = $s", id=document_id, s=status
        )

    # -- extraction stage -------------------------------------------------------------
    def clause_status(self, document_id: str, clause_key: str) -> Optional[str]:
        rows = self.client.read(
            "MATCH (c:Checkpoint {key: $key}) RETURN c.status AS status", key=f"{document_id}:{clause_key}"
        )
        return rows[0]["status"] if rows else None

    def save_clause(self, document_id: str, batch: ClauseBatch) -> None:
        mention_rows = [m.to_node_props() for m in batch.mentions]
        prop_rows = [
            {"props": p.to_node_props(), "mention_id": mid}
            for p in batch.propositions
            for mid in p.mention_ids
        ]
        entity_rows = [e.to_node_props() for e in batch.entities]
        subj = [{"pid": p.proposition_id, "eid": p.subject_entity_id} for p in batch.propositions if p.subject_entity_id]
        obj = [{"pid": p.proposition_id, "eid": p.object_entity_id} for p in batch.propositions if p.object_entity_id]

        def work(tx):
            if mention_rows:
                tx.run(_Q_MENTIONS, doc=document_id, rows=mention_rows)
            if entity_rows:
                tx.run(_Q_ENTITIES, rows=entity_rows)
            if prop_rows:
                tx.run(_Q_PROPOSITIONS, rows=prop_rows)
            if subj:
                tx.run(_Q_SUBJECT_LINKS, rows=subj)
            if obj:
                tx.run(_Q_OBJECT_LINKS, rows=obj)
            tx.run(_Q_CLEAR_QUARANTINE, qid=stable_id("quar", document_id, batch.clause_key))
            tx.run(
                _Q_CHECKPOINT,
                doc=document_id,
                key=f"{document_id}:{batch.clause_key}",
                clause=batch.clause_key,
                status=CHECKPOINT_DONE,
            )

        self.client.write(work)

    def quarantine_clause(self, document_id: str, clause_key: str, error: str, raw: str) -> None:
        qid = stable_id("quar", document_id, clause_key)

        def work(tx):
            tx.run(_Q_QUARANTINE, doc=document_id, qid=qid, clause=clause_key, error=error, raw=raw)
            tx.run(
                _Q_CHECKPOINT,
                doc=document_id,
                key=f"{document_id}:{clause_key}",
                clause=clause_key,
                status=CHECKPOINT_QUARANTINED,
            )

        self.client.write(work)

    def count_clauses(self, document_id: str) -> dict[str, int]:
        rows = self.client.read(
            "MATCH (c:Checkpoint {document_id: $id}) RETURN c.status AS status, count(*) AS n", id=document_id
        )
        return {r["status"]: r["n"] for r in rows}

    # -- reads --------------------------------------------------------------------------
    def load_mentions(self, document_id: str) -> list[Mention]:
        rows = self.client.read(
            "MATCH (:Document {document_id: $id})-[:CONTAINS]->(m:Mention) "
            "RETURN m ORDER BY m.start_offset, m.end_offset",
            id=document_id,
        )
        return [Mention.from_node_props(r["m"]) for r in rows]

    def load_propositions(self, document_id: str) -> list[Proposition]:
        rows = self.client.read(
            """
            MATCH (m:Mention)-[:EXPRESSES]->(p:Proposition {document_id: $id})
            OPTIONAL MATCH (p)-[:SUBJECT_ENTITY]->(s:Entity)
            OPTIONAL MATCH (p)-[:OBJECT_ENTITY]->(o:Entity)
            RETURN p, m.mention_id AS mention_id, m.start_offset AS start,
                   s.entity_id AS subject_entity_id, o.entity_id AS object_entity_id
            ORDER BY start
            """,
            id=document_id,
        )
        ordered: dict[str, dict] = {}
        for r in rows:
            pid = r["p"]["proposition_id"]
            slot = ordered.setdefault(
                pid,
                {"p": r["p"], "mentions": [], "s": r["subject_entity_id"], "o": r["object_entity_id"]},
            )
            if r["mention_id"] not in slot["mentions"]:
                slot["mentions"].append(r["mention_id"])
        return [Proposition.from_node_props(v["p"], v["mentions"], v["s"], v["o"]) for v in ordered.values()]

    def load_entities(self, document_id: str) -> list[Entity]:
        rows = self.client.read(
            "MATCH (e:Entity {document_id: $id}) RETURN e ORDER BY e.canonical_name", id=document_id
        )
        return [Entity.from_node_props(r["e"]) for r in rows]

    def load_relations(self, document_id: str) -> list[Relation]:
        rows = self.client.read(
            """
            MATCH (a:Proposition {document_id: $id})-[r]->(b:Proposition {document_id: $id})
            WHERE type(r) IN $types
            RETURN a.proposition_id AS source, b.proposition_id AS target, type(r) AS type, properties(r) AS props
            ORDER BY source, target, type
            """,
            id=document_id,
            types=SEMANTIC_TYPES,
        )
        return [
            Relation(
                source_id=r["source"],
                target_id=r["target"],
                relation_type=RelationType(r["type"]),
                method=r["props"].get("method", "unknown"),
                confidence=float(r["props"].get("confidence", 0.0)),
                evidence=r["props"].get("evidence") or ["(none recorded)"],
                rationale=r["props"].get("rationale"),
            )
            for r in rows
        ]

    def load_quarantine(self, document_id: str) -> list[dict]:
        return self.client.read(
            "MATCH (q:Quarantine {document_id: $id}) "
            "RETURN q.clause_key AS clause_key, q.error AS error, q.raw_response AS raw_response ORDER BY clause_key",
            id=document_id,
        )

    # -- resolution stage -------------------------------------------------------------
    def save_resolution(self, document_id: str, props: list[Proposition], relations: list[Relation]) -> None:
        ref_rows = [
            {"pid": p.proposition_id, "refs": json.dumps([r.model_dump(mode="json") for r in p.references])}
            for p in props
        ]
        by_type: dict[str, list[dict]] = {}
        for rel in relations:
            by_type.setdefault(rel.relation_type.value, []).append(
                {"source": rel.source_id, "target": rel.target_id, "props": rel.to_edge_props()}
            )

        def work(tx):
            tx.run(
                "MATCH (:Proposition {document_id: $doc})-[r]->(:Proposition {document_id: $doc}) "
                "WHERE type(r) IN $types DELETE r",
                doc=document_id,
                types=SEMANTIC_TYPES,
            )
            if ref_rows:
                tx.run(
                    "UNWIND $rows AS row MATCH (p:Proposition {proposition_id: row.pid}) "
                    "SET p.references_json = row.refs",
                    rows=ref_rows,
                )
            for rtype, rows in by_type.items():
                assert re.fullmatch(r"[A-Z_]+", rtype) and rtype in SEMANTIC_TYPES  # safe to inline
                tx.run(
                    "UNWIND $rows AS row "
                    "MATCH (a:Proposition {proposition_id: row.source}), (b:Proposition {proposition_id: row.target}) "
                    f"MERGE (a)-[x:{rtype}]->(b) SET x += row.props",
                    rows=rows,
                )

        self.client.write(work)
