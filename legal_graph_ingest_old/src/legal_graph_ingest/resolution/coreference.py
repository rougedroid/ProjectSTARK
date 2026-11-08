"""Stage 7a: link references to earlier propositions using the *completed* graph.

Policy: resolve only when exactly one plausible antecedent exists (or an optional adjudicator is
confident). Otherwise the reference stays unresolved with its candidates recorded.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from ..models.proposition import Proposition
from ..models.relation import Relation, RelationType

log = logging.getLogger(__name__)

# adjudicator(prop, reference, candidate_propositions) -> (chosen_id | None, confidence, method)
Adjudicator = Callable[..., Optional[tuple[Optional[str], float, str]]]


def resolve_references(
    props: list[Proposition],
    adjudicator: Optional[Adjudicator] = None,
    min_adjudication_confidence: float = 0.8,
) -> list[Relation]:
    by_id = {p.proposition_id: p for p in props}
    relations: list[Relation] = []

    for p in props:
        for ref in p.references:
            ref.resolved_id = ref.method = ref.confidence = None  # recompute from scratch (idempotent)
            candidates = [c for c in dict.fromkeys(ref.candidate_ids) if c in by_id and c != p.proposition_id]
            ref.candidate_ids = candidates

            chosen: Optional[str] = None
            confidence = 0.0
            method = ""
            if len(candidates) == 1:
                chosen, method = candidates[0], "single-candidate"
                confidence = round(0.7 + 0.2 * p.extraction_confidence, 3)
            elif len(candidates) > 1 and adjudicator is not None:
                verdict = adjudicator(p, ref, [by_id[c] for c in candidates])
                if verdict and verdict[0] in candidates and verdict[1] >= min_adjudication_confidence:
                    chosen, confidence, method = verdict[0], verdict[1], verdict[2]

            if chosen is None:
                continue  # stays unresolved; candidates recorded
            ref.resolved_id, ref.confidence, ref.method = chosen, confidence, method
            target = by_id[chosen]
            relations.append(
                Relation(
                    source_id=p.proposition_id,
                    target_id=chosen,
                    relation_type=RelationType.REFERS_TO,
                    method=method,
                    confidence=min(confidence, 1.0),
                    evidence=[ref.surface_text, p.source_quote, target.source_quote],
                    rationale=f"reference {ref.surface_text!r} resolved to a single antecedent"
                    if method == "single-candidate"
                    else f"reference {ref.surface_text!r} adjudicated",
                )
            )
    return relations
