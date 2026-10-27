import json

import pytest

import legal_graph_ingest as lgi
from legal_graph_ingest import GraphIngestor, ingest_pdf

from conftest import FakeBackend, scripted_responder


def test_public_names_are_importable():
    for name in ["GraphIngestor", "ingest_pdf", "Settings", "Proposition", "Relation", "RelationType"]:
        assert hasattr(lgi, name)


def test_graph_ingestor_as_a_library(contract_pdf):
    seen = []
    with GraphIngestor(in_memory=True, ollama_model="fake", ollama_backend=FakeBackend(scripted_responder)) as g:
        report = g.ingest(contract_pdf, progress=lambda n, total, head: seen.append((n, total)))
        assert seen[0] == (1, 4) and seen[-1] == (4, 4)
        assert len(g.propositions(report.document_id)) == 7
        assert g.document(report.document_id).ingestion_status == "resolved"
        assert any(r.relation_type.value == "EXCEPTS_FROM" for r in g.relations(report.document_id))
        json.dumps(g.snapshot(report.document_id), default=str)


def test_ingest_pdf_one_call(contract_pdf):
    doc = ingest_pdf(contract_pdf, in_memory=True, ollama_model="fake", ollama_backend=FakeBackend(scripted_responder))
    assert doc.document_id == doc.report.document_id
    assert len(doc.propositions) == 7 and doc.mentions and doc.entities and doc.relations
    assert all(p.mention_ids for p in doc.propositions)


def test_reading_an_existing_graph_needs_no_ollama(contract_pdf):
    from legal_graph_ingest import InMemoryRepository

    repo = InMemoryRepository()
    with GraphIngestor(repository=repo, ollama_model="fake", ollama_backend=FakeBackend(scripted_responder)) as g:
        doc_id = g.ingest(contract_pdf).document_id
    with GraphIngestor(repository=repo) as reader:      # no model configured
        assert len(reader.propositions(doc_id)) == 7
        rep = reader.resolve(doc_id)                      # re-resolve also needs no model
        assert rep.status == "resolved"


def test_settings_overrides_and_missing_model():
    from legal_graph_ingest.config import ConfigError

    g = GraphIngestor(in_memory=True, max_retries=5)
    assert g.settings.max_retries == 5
    with pytest.raises(ConfigError):
        g.ingest("whatever.pdf")
