"""Read-only Neo4j graph facade for reasoning operators."""
from __future__ import annotations
from collections.abc import Iterator
from .models import Document, Entity, Mention, Pattern, Proposition, SemanticEdge, Evidence

RELATIONS = frozenset({"REFERS_TO", "QUALIFIES", "EXCEPTS_FROM", "SUPPORTS", "CONTRADICTS", "DUPLICATE_OF"})

def _entity(d):
    if d is None: return None
    p = dict(d)
    p["aliases"] = tuple(p.get("aliases") or ())
    return Entity(**{k: v for k, v in p.items() if k in Entity.__dataclass_fields__})

def _mention(d):
    return Mention(**{k: v for k, v in dict(d).items() if k in Mention.__dataclass_fields__})

class KnowledgeGraph:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j", document_ids: list[str] | None = None):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
        self.document_ids = list(document_ids or [])
    @classmethod
    def from_env(cls, document_ids: list[str] | None = None) -> KnowledgeGraph:
        import os
        return cls(os.environ.get("NEO4J_URI", "bolt://localhost:7687"), os.environ.get("NEO4J_USERNAME", "neo4j"), os.environ["NEO4J_PASSWORD"], os.environ.get("NEO4J_DATABASE", "neo4j"), document_ids)
    def close(self): self.driver.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def _read(self, query: str, **params) -> list[dict]:
        with self.driver.session(database=self.database) as session:
            return [dict(r) for r in session.run(query, **params)]
    def facts(self, limit: int = 1000, document_ids: list[str] | None = None) -> list[Proposition]:
        docs = self.document_ids if document_ids is None else document_ids
        rows = self._read("MATCH (p:Proposition) WHERE size($docs) = 0 OR p.document_id IN $docs RETURN properties(p) AS p ORDER BY p.proposition_id LIMIT $limit", docs=docs, limit=limit)
        return [Proposition.from_neo4j(r["p"]) for r in rows]
    def count_facts(self, document_ids: list[str] | None = None) -> int:
        docs = self.document_ids if document_ids is None else document_ids
        return self._read("MATCH (p:Proposition) WHERE size($docs)=0 OR p.document_id IN $docs RETURN count(p) AS n", docs=docs)[0]["n"]
    def get_fact(self, proposition_id: str) -> Proposition | None:
        rows = self._read("MATCH (p:Proposition {proposition_id:$id}) WHERE size($docs)=0 OR p.document_id IN $docs RETURN properties(p) AS p", id=proposition_id, docs=self.document_ids)
        return Proposition.from_neo4j(rows[0]["p"]) if rows else None
    def match(self, pattern: Pattern, limit: int = 1000, document_ids: list[str] | None = None) -> list[tuple[Proposition, dict[str, str]]]:
        """?variables bind across subject/predicate/object; repeated variables must agree."""
        docs = self.document_ids if document_ids is None else document_ids
        parts = pattern.as_tuple()
        filters = [None if s.startswith("?") else s for s in parts]
        rows = self._read("MATCH (p:Proposition) WHERE (size($docs)=0 OR p.document_id IN $docs) AND ($s IS NULL OR p.subject=$s) AND ($v IS NULL OR p.predicate=$v) AND ($o IS NULL OR p.object=$o) RETURN properties(p) AS p ORDER BY p.proposition_id LIMIT $limit", docs=docs, s=filters[0], v=filters[1], o=filters[2], limit=limit)
        out = []
        for r in rows:
            p = Proposition.from_neo4j(r["p"])
            bindings = {}
            for token, value in zip(parts, p.pattern().as_tuple()):
                if token.startswith("?"):
                    if token in bindings and bindings[token] != value: break
                    bindings[token] = value
            else: out.append((p, bindings))
        return out
    def edges(self, proposition_id: str | None = None, relation: str | None = None, direction: str = "out", limit: int = 1000) -> list[SemanticEdge]:
        if relation is not None and relation not in RELATIONS: raise ValueError("Unsupported semantic relationship")
        if direction not in ("in", "out", "both"): raise ValueError("direction must be in/out/both")
        arrow = {"out": "(a)-[r]->(b)", "in": "(a)<-[r]-(b)", "both": "(a)-[r]-(b)"}[direction]
        query = f"MATCH {arrow} WHERE a:Proposition AND b:Proposition AND ($id IS NULL OR a.proposition_id=$id) AND ($rel IS NULL OR type(r)=$rel) AND (size($docs)=0 OR (a.document_id IN $docs AND b.document_id IN $docs)) RETURN startNode(r).proposition_id AS source, endNode(r).proposition_id AS target, type(r) AS relation, properties(r) AS props LIMIT $limit"
        rows = self._read(query, id=proposition_id, rel=relation, docs=self.document_ids, limit=limit)
        return [SemanticEdge(r["source"], r["target"], r["relation"], r["props"].get("method", ""), r["props"].get("confidence"), tuple(r["props"].get("evidence") or ()), r["props"].get("rationale", "")) for r in rows]
    def provenance(self, proposition_id: str) -> Evidence | None:
        p = self.get_fact(proposition_id)
        if p is None: return None
        mentions = self._read("MATCH (m:Mention)-[:EXPRESSES]->(p:Proposition {proposition_id:$id}) RETURN properties(m) AS m ORDER BY m.page_start, m.start_offset", id=proposition_id)
        entities = self._read("MATCH (p:Proposition {proposition_id:$id})-[r:SUBJECT_ENTITY|OBJECT_ENTITY]->(e:Entity) RETURN type(r) AS role, properties(e) AS e", id=proposition_id)
        return Evidence(p, tuple(_mention(r["m"]) for r in mentions), tuple(_entity(r["e"]) for r in entities if r["role"] == "SUBJECT_ENTITY"), tuple(_entity(r["e"]) for r in entities if r["role"] == "OBJECT_ENTITY"))
    def documents(self) -> list[Document]:
        rows = self._read("MATCH (d:Document) WHERE size($docs)=0 OR d.document_id IN $docs RETURN properties(d) AS d", docs=self.document_ids)
        return [Document(**{k:v for k,v in r["d"].items() if k in Document.__dataclass_fields__}) for r in rows]
    def rules(self, limit: int = 5000):
        """Project only explicit structured rules; no free-text interpretation."""
        from .reasoning import project_rules
        return project_rules(self.facts(limit=limit))[0]
