from legal_graph_ingest.models.document import DocumentRecord
from legal_graph_ingest.models.mention import Mention
from legal_graph_ingest.models.proposition import Entity, Proposition
from legal_graph_ingest.storage.memory import InMemoryRepository
from legal_graph_ingest.storage.repository import ClauseBatch, Neo4jRepository


def _batch(clause_key="c1"):
    m = Mention(mention_id="men_1", document_id="doc_1", page_start=1, page_end=1, start_offset=0,
                end_offset=10, source_text="The Supplier shall deliver")
    p = Proposition(
        local_id="p1", subject="Supplier", predicate="deliver", object="Equipment",
        normalized_text="The Supplier must deliver the Equipment.", modality="obligation",
        source_quote="The Supplier shall deliver", proposition_id="prop_1", document_id="doc_1",
        clause_key=clause_key, mention_ids=["men_1"], subject_entity_id="ent_1",
    )
    e = Entity(entity_id="ent_1", document_id="doc_1", canonical_name="Supplier", entity_type="party")
    return ClauseBatch(clause_key, [m], [p], [e])


def test_in_memory_repository_is_idempotent():
    repo = InMemoryRepository()
    repo.upsert_document(DocumentRecord("doc_1", "a.pdf", "sha", 1))
    for _ in range(3):
        repo.save_clause("doc_1", _batch())
    assert len(repo.load_mentions("doc_1")) == 1
    assert len(repo.load_propositions("doc_1")) == 1
    assert len(repo.load_entities("doc_1")) == 1
    assert repo.clause_status("doc_1", "c1") == "done"


def test_quarantine_does_not_store_propositions():
    repo = InMemoryRepository()
    repo.upsert_document(DocumentRecord("doc_1", "a.pdf", "sha", 1))
    repo.quarantine_clause("doc_1", "c1", "bad json", "{broken")
    assert repo.clause_status("doc_1", "c1") == "quarantined"
    assert repo.load_propositions("doc_1") == []
    assert repo.load_quarantine("doc_1")[0]["raw_response"] == "{broken"


class _FakeTx:
    def __init__(self):
        self.queries = []

    def run(self, query, **params):
        self.queries.append((query, params))


class _FakeClient:
    def __init__(self):
        self.tx = _FakeTx()
        self.write_calls = 0

    def write(self, work):
        self.write_calls += 1
        return work(self.tx)


def test_neo4j_save_clause_is_one_transaction_with_checkpoint_last():
    client = _FakeClient()
    Neo4jRepository(client).save_clause("doc_1", _batch())
    assert client.write_calls == 1
    queries = [q for q, _ in client.tx.queries]
    assert "MERGE (m:Mention" in queries[0]
    assert any("EXPRESSES" in q for q in queries)
    assert any("SUBJECT_ENTITY" in q for q in queries)
    assert "Checkpoint" in queries[-1]
    assert all("MERGE" in q for q in queries if "DELETE" not in q)  # re-runs cannot duplicate records


def test_neo4j_resolution_replaces_inferred_edges_inside_one_transaction():
    from legal_graph_ingest.models.relation import Relation, RelationType

    client = _FakeClient()
    rel = Relation(source_id="a", target_id="b", relation_type=RelationType.EXCEPTS_FROM,
                   method="reference-rule", confidence=0.8, evidence=["q"])
    Neo4jRepository(client).save_resolution("doc_1", [], [rel])
    queries = [q for q, _ in client.tx.queries]
    assert client.write_calls == 1
    assert "DELETE r" in queries[0]
    assert "EXCEPTS_FROM" in queries[-1]
