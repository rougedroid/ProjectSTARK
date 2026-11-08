import json

import pytest

from legal_graph_ingest.extraction.ollama_client import ExtractionFailure, OllamaExtractor
from legal_graph_ingest.extraction.context import ContextBuilder, ContextMemory
from legal_graph_ingest.extraction.segmenter import segment, sentence_spans
from legal_graph_ingest.validation.schema import ValidationFailure, parse_extraction

from conftest import FakeBackend

TEXT = (
    "SUPPLY AGREEMENT\n\n"
    "8. DELIVERY\n\n"
    "8.1 The Supplier shall deliver the Equipment within 30 days. The foregoing obligation does not apply.\n\n"
    "8.2 Inc. and Ltd. are abbreviations. Another sentence follows."
)


def test_segmenter_clauses_and_offsets():
    clauses = segment(TEXT)
    assert [c.clause_number for c in clauses] == [None, "8.1", "8.2"]
    assert clauses[1].section == "8 DELIVERY"
    for c in clauses:
        assert TEXT[c.start:c.end] == c.text
        for s in c.sentences:
            assert TEXT[s.start:s.end] == s.text


def test_sentence_splitting_respects_abbreviations():
    spans = sentence_spans("Inc. and Ltd. are abbreviations. Another sentence follows.")
    assert len(spans) == 2


def test_oversized_clause_is_split_on_paragraph_boundaries():
    para = "8.1 " + "Word " * 100 + "end.\n\n" + "Second paragraph of the same clause. " * 5
    clauses = segment(para, max_chars=300)
    assert len(clauses) >= 2


def test_pdf_reader_extracts_text_with_pages(contract_pdf):
    from legal_graph_ingest.extraction.pdf_reader import read_pdf

    doc = read_pdf(contract_pdf)
    assert doc.page_count == 2
    assert "8.1 The Supplier shall deliver" in doc.text.replace("\n", " ")
    assert doc.page_for_offset(doc.text.index("10.1")) == 2
    assert len(doc.sha256) == 64


def _ctx():
    clause = segment(TEXT)[1]
    return ContextBuilder().build(clause, ContextMemory())


def _valid_json():
    return json.dumps({"propositions": [{
        "local_id": "p1", "subject": "Supplier", "predicate": "deliver", "object": "Equipment",
        "normalized_text": "The Supplier must deliver the Equipment.", "modality": "obligation",
        "source_quote": "The Supplier shall deliver the Equipment within 30 days.",
    }]})


def test_extractor_retries_then_succeeds(settings):
    answers = iter(["not json at all", _valid_json()])
    backend = FakeBackend(lambda messages: next(answers))
    extractor = OllamaExtractor(settings, backend)
    result = extractor.extract(_ctx(), parse_extraction)
    assert result.propositions[0].subject == "Supplier"
    assert len(backend.calls) == 2
    assert "invalid" in backend.calls[1][-1]["content"]  # feedback was sent back to the model


def test_extractor_raises_after_retries_so_caller_can_quarantine(settings):
    backend = FakeBackend(lambda messages: "{broken")
    extractor = OllamaExtractor(settings, backend)
    with pytest.raises(ExtractionFailure) as err:
        extractor.extract(_ctx(), parse_extraction)
    assert err.value.raw == "{broken"
    assert len(backend.calls) == settings.max_retries


def test_extractor_requires_model():
    from legal_graph_ingest.config import ConfigError, Settings

    with pytest.raises(ConfigError):
        OllamaExtractor(Settings(ollama_model=""), FakeBackend(lambda m: ""))
