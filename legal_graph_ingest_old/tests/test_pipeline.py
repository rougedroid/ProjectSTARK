import json

import pytest

from legal_graph_ingest.export.json_export import build_snapshot, write_json
from legal_graph_ingest.extraction.ollama_client import OllamaExtractor
from legal_graph_ingest.models.proposition import Proposition
from legal_graph_ingest.models.relation import RelationType
from legal_graph_ingest.pipeline import IngestPipeline
from legal_graph_ingest.resolution.coreference import resolve_references
from legal_graph_ingest.resolution.duplicates import find_duplicates
from legal_graph_ingest.storage.memory import InMemoryRepository

from conftest import FakeBackend, scripted_responder


def _pipeline(settings, responder=scripted_responder, repo=None):
    repo = repo or InMemoryRepository()
    extractor = OllamaExtractor(settings, FakeBackend(responder))
    return IngestPipeline(settings, repo, extractor), repo


def test_full_pipeline_provenance_and_relations(settings, contract_pdf):
    pipe, repo = _pipeline(settings)
    report = pipe.ingest(contract_pdf)
    assert report.status == "resolved"
    assert report.clauses_quarantined == 0

    doc_id = report.document_id
    props = repo.load_propositions(doc_id)
    mentions = {m.mention_id: m for m in repo.load_mentions(doc_id)}
    assert len(props) == 7

    # every proposition has a verifiable source passage with page and clause references
    for p in props:
        assert p.mention_ids
        m = mentions[p.mention_ids[0]]
        assert p.source_quote.split()[0] in m.source_text
        assert m.page_start >= 1 and m.clause_number
    clause_10 = next(m for m in mentions.values() if m.clause_number == "10.1")
    assert clause_10.page_start == 2

    # "foregoing obligation" -> single antecedent -> resolved, exception edge with evidence
    by_text = {p.normalized_text: p for p in props}
    exc = by_text["The delivery obligation does not apply when delivery is prevented by a Force Majeure Event."]
    base = by_text["The Supplier must deliver the Equipment within 30 days of receiving payment."]
    rels = repo.load_relations(doc_id)
    excepts = [r for r in rels if r.relation_type == RelationType.EXCEPTS_FROM]
    assert [(r.source_id, r.target_id) for r in excepts] == [(exc.proposition_id, base.proposition_id)]
    assert excepts[0].evidence and excepts[0].method and 0 < excepts[0].confidence <= 1

    # two plausible antecedents -> stays unresolved, candidates recorded, no edge created
    ambiguous = by_text["An obligation survives termination."]
    ref = ambiguous.references[0]
    assert ref.resolved_id is None and len(ref.candidate_ids) == 2
    assert not [r for r in rels if r.source_id == ambiguous.proposition_id]
    assert report.unresolved_references == 1

    # temporal qualification of the insurance obligation
    qualifies = [r for r in rels if r.relation_type == RelationType.QUALIFIES]
    assert len(qualifies) == 1

    # entities: canonical parties exist; abstract subjects stay entity-less
    names = {e.canonical_name for e in repo.load_entities(doc_id)}
    assert {"Supplier", "Buyer", "Equipment", "Price"} <= names
    assert exc.subject_entity_id is None


def test_rerun_does_not_duplicate_records_and_resumes_from_checkpoints(settings, contract_pdf):
    pipe, repo = _pipeline(settings)
    first = pipe.ingest(contract_pdf)
    counts = (len(repo.mentions), len(repo.propositions), len(repo.entities), len(repo.relations))

    second_pipe, _ = _pipeline(settings, repo=repo)
    second = second_pipe.ingest(contract_pdf)
    assert second.clauses_skipped == second.clauses_total
    assert second.clauses_extracted == 0
    assert (len(repo.mentions), len(repo.propositions), len(repo.entities), len(repo.relations)) == counts
    assert second.document_id == first.document_id


def test_interrupted_run_resumes_without_duplicates(settings, contract_pdf):
    pipe, repo = _pipeline(settings)
    partial = pipe.extract(contract_pdf, max_clauses=2)
    assert partial.status == "extracting"
    with pytest.raises(RuntimeError):          # relations only after extraction has completed
        pipe.resolve(partial.document_id)

    pipe2, _ = _pipeline(settings, repo=repo)
    final = pipe2.ingest(contract_pdf)
    assert final.clauses_skipped == 2
    assert len(repo.propositions) == 7
    assert final.status == "resolved"


def test_invalid_responses_are_quarantined_not_accepted(settings, contract_pdf):
    def bad_for_insurance(messages):
        if "HEADING: 9 INSURANCE / 9.1" in messages[1]["content"]:
            return json.dumps({"propositions": [{
                "local_id": "p1", "subject": "Supplier", "predicate": "maintain",
                "normalized_text": "invented", "modality": "obligation",
                "source_quote": "This sentence does not appear in the contract at all.",
            }]})
        return scripted_responder(messages)

    pipe, repo = _pipeline(settings, bad_for_insurance)
    report = pipe.ingest(contract_pdf)
    assert report.clauses_quarantined == 1
    assert report.status == "resolved"
    assert len(repo.propositions) == 5          # nothing from the quarantined clause was stored
    q = repo.load_quarantine(report.document_id)
    assert len(q) == 1 and "verbatim" in q[0]["error"]

    # retrying quarantined clauses after the model improves
    pipe2, _ = _pipeline(settings, repo=repo)
    retry = pipe2.extract(contract_pdf, retry_quarantined=True)
    assert retry.clauses_extracted == 1 and len(repo.propositions) == 7


def test_export_snapshot_is_complete_and_json_serialisable(settings, contract_pdf, tmp_path):
    pipe, repo = _pipeline(settings)
    report = pipe.ingest(contract_pdf)
    snap = build_snapshot(repo, report.document_id)
    types = {e["type"] for e in snap["relationships"]}
    assert {"CONTAINS", "EXPRESSES", "SUBJECT_ENTITY", "OBJECT_ENTITY", "EXCEPTS_FROM", "QUALIFIES"} <= types
    out = write_json(repo, report.document_id, tmp_path / "graph.json")
    assert json.loads(out.read_text())["document"]["document_id"] == report.document_id


def _prop(pid, text, refs=None, **kw):
    return Proposition(
        local_id=pid, subject=kw.get("subject", "Supplier"), predicate="deliver", normalized_text=text,
        modality="obligation", source_quote=f"quote for {pid}", proposition_id=pid, document_id="d",
        clause_key="c", mention_ids=[f"m_{pid}"], references=refs or [],
    )


def test_duplicate_detection_links_without_merging():
    a = _prop("a", "The Supplier must deliver the Equipment within 30 days.")
    b = _prop("b", "The Supplier must deliver the Equipment within 30 days!")
    c = _prop("c", "The Supplier must insure the premises against all fire damage.")
    rels = find_duplicates([a, b, c], threshold=0.92)
    assert [(r.source_id, r.target_id, r.relation_type) for r in rels] == [("b", "a", RelationType.DUPLICATE_OF)]
    assert a.normalized_text.endswith("days.") and b.normalized_text.endswith("days!")  # text untouched


def test_coreference_leaves_ambiguity_unresolved_unless_adjudicated():
    from legal_graph_ingest.models.proposition import Reference

    a, b = _prop("a", "A"), _prop("b", "B")
    c = _prop("c", "C", refs=[Reference(surface_text="it", candidate_ids=["a", "b"])])
    assert resolve_references([a, b, c]) == []
    assert c.references[0].resolved_id is None

    rels = resolve_references([a, b, c], adjudicator=lambda p, r, cands: ("b", 0.9, "llm:test"))
    assert c.references[0].resolved_id == "b" and rels[0].method == "llm:test"

    resolve_references([a, b, c], adjudicator=lambda p, r, cands: ("b", 0.4, "llm:test"))
    assert c.references[0].resolved_id is None   # low confidence -> not forced
