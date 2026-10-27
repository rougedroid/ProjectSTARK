import json

import pytest

from legal_graph_ingest.models.proposition import ExtractedProposition, Reference
from legal_graph_ingest.validation.evidence import locate_quote
from legal_graph_ingest.validation.references import validate_references
from legal_graph_ingest.validation.schema import ValidationFailure, parse_extraction

TEXT = "8.1 The Supplier shall deliver the\nEquipment within  30 days \u2014 of \u201creceiving\u201d payment. Next."


def _prop(local_id="p1", refs=None):
    return ExtractedProposition(
        local_id=local_id, subject="Supplier", predicate="deliver", normalized_text="x",
        modality="obligation", source_quote="The Supplier shall deliver", references=refs or [],
    )


def test_exact_quote_located():
    s, e = locate_quote("The Supplier shall deliver the", TEXT)
    assert TEXT[s:e] == "The Supplier shall deliver the"


def test_whitespace_and_typography_insensitive_match_maps_back_to_original_offsets():
    quote = 'deliver the Equipment within 30 days - of "receiving" payment.'
    s, e = locate_quote(quote, TEXT)
    assert TEXT[s:e].startswith("deliver the")
    assert TEXT[s:e].endswith("payment.")


def test_hallucinated_or_too_short_quote_is_rejected():
    assert locate_quote("The Buyer shall pay the Price immediately", TEXT) is None
    assert locate_quote("abc", TEXT) is None


def test_quote_must_be_inside_the_clause_window():
    assert locate_quote("The Supplier shall deliver the", TEXT, start=40) is None


def test_parse_rejects_bad_json_and_schema_violations():
    for raw in ["", "nope", json.dumps({"propositions": [{"local_id": "p1"}]})]:
        with pytest.raises(ValidationFailure):
            parse_extraction(raw)


def test_parse_accepts_fenced_json_and_empty_result():
    assert parse_extraction("```json\n{\"propositions\": []}\n```").propositions == []


def test_parse_rejects_duplicate_local_ids():
    one = {
        "local_id": "p1", "subject": "S", "predicate": "p", "normalized_text": "t",
        "modality": "obligation", "source_quote": "quote text here",
    }
    with pytest.raises(ValidationFailure):
        parse_extraction(json.dumps({"propositions": [one, one]}))


def test_unknown_candidates_are_dropped_not_invented():
    ref = Reference(surface_text="it", candidate_ids=["ghost", "known_1", "local:p2", "p2"])
    p1, p2 = _prop("p1", [ref]), _prop("p2")
    errors = validate_references([p1, p2], {"known_1"})
    assert errors == []
    assert p1.references[0].candidate_ids == ["known_1", "local:p2"]


def test_self_reference_is_an_error():
    p1 = _prop("p1", [Reference(surface_text="it", candidate_ids=["local:p1"])])
    assert validate_references([p1], set())
