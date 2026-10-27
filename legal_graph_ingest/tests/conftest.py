import json

import pytest

from legal_graph_ingest.config import Settings

CONTRACT_BLOCKS = [
    [
        "SUPPLY AGREEMENT",
        "8. DELIVERY",
        "8.1 The Supplier shall deliver the Equipment within 30 days of receiving payment. "
        "The foregoing obligation does not apply where delivery is prevented by a Force Majeure Event.",
        "9. INSURANCE",
        "9.1 The Supplier shall maintain insurance coverage. The foregoing obligation shall continue until delivery.",
    ],
    [
        "10. PAYMENT",
        "10.1 The Buyer shall pay the Price. The Supplier shall deliver the Equipment. "
        "This obligation survives termination.",
    ],
]

RESPONSES = {
    "HEADING: 8 DELIVERY / 8.1": {
        "propositions": [
            {
                "local_id": "p1", "subject": "Supplier", "predicate": "deliver", "object": "Equipment",
                "normalized_text": "The Supplier must deliver the Equipment within 30 days of receiving payment.",
                "modality": "obligation", "polarity": "positive", "conditions": ["payment received"],
                "temporal_scope": "within 30 days of receiving payment", "extraction_confidence": 0.9,
                "source_quote": "The Supplier shall deliver the Equipment within 30 days of receiving payment.",
            },
            {
                "local_id": "p2", "subject": "the obligation to deliver Equipment", "predicate": "does_not_apply_when",
                "object": "delivery prevented by a Force Majeure Event",
                "normalized_text": "The delivery obligation does not apply when delivery is prevented by a Force Majeure Event.",
                "modality": "exception", "extraction_confidence": 0.85,
                "source_quote": "The foregoing obligation does not apply where delivery is prevented by a Force Majeure Event.",
                "references": [{"surface_text": "The foregoing obligation", "kind": "anaphoric_phrase", "candidate_ids": ["local:p1"]}],
            },
        ]
    },
    "HEADING: 9 INSURANCE / 9.1": {
        "propositions": [
            {
                "local_id": "p1", "subject": "Supplier", "predicate": "maintain", "object": "insurance coverage",
                "normalized_text": "The Supplier must maintain insurance coverage.",
                "modality": "obligation", "extraction_confidence": 0.9,
                "source_quote": "The Supplier shall maintain insurance coverage.",
            },
            {
                "local_id": "p2", "subject": "the obligation to maintain insurance coverage", "predicate": "continues_until",
                "object": "delivery", "normalized_text": "The insurance obligation continues until delivery.",
                "modality": "obligation", "temporal_scope": "until delivery", "extraction_confidence": 0.8,
                "source_quote": "The foregoing obligation shall continue until delivery.",
                "references": [{"surface_text": "The foregoing obligation", "kind": "anaphoric_phrase", "candidate_ids": ["local:p1"]}],
            },
        ]
    },
    "HEADING: 10 PAYMENT / 10.1": {
        "propositions": [
            {
                "local_id": "p1", "subject": "Buyer", "predicate": "pay", "object": "Price",
                "normalized_text": "The Buyer must pay the Price.", "modality": "obligation",
                "source_quote": "The Buyer shall pay the Price.",
            },
            {
                "local_id": "p2", "subject": "Supplier", "predicate": "deliver", "object": "Equipment",
                "normalized_text": "The Supplier must deliver the Equipment.", "modality": "obligation",
                "source_quote": "The Supplier shall deliver the Equipment.",
            },
            {
                "local_id": "p3", "subject": "This obligation", "predicate": "survives", "object": "termination",
                "normalized_text": "An obligation survives termination.", "modality": "statement",
                "source_quote": "This obligation survives termination.",
                "references": [{"surface_text": "This obligation", "kind": "anaphoric_phrase",
                                "candidate_ids": ["local:p1", "local:p2"]}],
            },
        ]
    },
}


class FakeBackend:
    """Stands in for the Ollama client. `responder(user_prompt) -> str`."""

    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def chat(self, *, model, messages, format, options):
        self.calls.append(messages)
        return {"message": {"content": self.responder(messages)}}


def scripted_responder(messages):
    prompt = messages[1]["content"]
    for marker, payload in RESPONSES.items():
        if marker in prompt:
            return json.dumps(payload)
    return json.dumps({"propositions": []})


@pytest.fixture
def settings():
    return Settings(ollama_model="fake-model", max_retries=2, neo4j_password="x")


@pytest.fixture
def contract_pdf(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    path = tmp_path / "contract.pdf"
    doc = pymupdf.open()
    for blocks in CONTRACT_BLOCKS:
        page = doc.new_page()
        y = 60
        for text in blocks:
            page.insert_textbox(pymupdf.Rect(72, y, 520, y + 80), text, fontsize=11)
            y += 95
    doc.save(str(path))
    doc.close()
    return path
