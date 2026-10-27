"""Stage 9: machine-readable graph snapshot for independent inspection and testing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..storage.repository import Repository


def build_snapshot(repo: Repository, document_id: str) -> dict[str, Any]:
    doc = repo.get_document(document_id)
    if doc is None:
        raise KeyError(f"unknown document_id: {document_id}")
    mentions = repo.load_mentions(document_id)
    props = repo.load_propositions(document_id)
    entities = repo.load_entities(document_id)
    relations = repo.load_relations(document_id)

    edges: list[dict[str, Any]] = [
        {"type": "CONTAINS", "source": document_id, "target": m.mention_id} for m in mentions
    ]
    for p in props:
        edges += [{"type": "EXPRESSES", "source": mid, "target": p.proposition_id} for mid in p.mention_ids]
        if p.subject_entity_id:
            edges.append({"type": "SUBJECT_ENTITY", "source": p.proposition_id, "target": p.subject_entity_id})
        if p.object_entity_id:
            edges.append({"type": "OBJECT_ENTITY", "source": p.proposition_id, "target": p.object_entity_id})
    for r in relations:
        edges.append(
            {
                "type": r.relation_type.value,
                "source": r.source_id,
                "target": r.target_id,
                "method": r.method,
                "confidence": r.confidence,
                "evidence": r.evidence,
                "rationale": r.rationale,
            }
        )

    return {
        "document": doc.to_node_props(),
        "mentions": [m.model_dump() for m in mentions],
        "propositions": [p.model_dump(mode="json") for p in props],
        "entities": [e.model_dump() for e in entities],
        "relationships": edges,
        "quarantined_clauses": repo.load_quarantine(document_id),
    }


def write_json(repo: Repository, document_id: str, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_snapshot(repo, document_id), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path
