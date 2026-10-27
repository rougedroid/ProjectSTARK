"""Stage 8: semantic relations, derived only from the completed, resolved graph."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional, Protocol

from ..models.proposition import Modality, Proposition
from ..models.relation import Relation, RelationType

log = logging.getLogger(__name__)


class PairClassifier(Protocol):
    method: str

    def classify(self, a: Proposition, b: Proposition): ...


def derive_structural_relations(props: list[Proposition]) -> list[Relation]:
    """Deterministic rules over *resolved* references."""
    by_id = {p.proposition_id: p for p in props}
    out: list[Relation] = []
    for p in props:
        for ref in p.references:
            if not ref.resolved_id or ref.resolved_id not in by_id:
                continue
            target = by_id[ref.resolved_id]
            base = ref.confidence or 0.5
            evidence = [ref.surface_text, p.source_quote, target.source_quote]
            if p.modality == Modality.EXCEPTION:
                rtype, conf, why = RelationType.EXCEPTS_FROM, base * 0.95, "exception clause with resolved antecedent"
            elif p.modality == Modality.CONDITION or p.temporal_scope or p.conditions:
                rtype, conf, why = RelationType.QUALIFIES, base * 0.8, "condition/time limit attached to resolved antecedent"
            else:
                continue
            out.append(
                Relation(
                    source_id=p.proposition_id,
                    target_id=target.proposition_id,
                    relation_type=rtype,
                    method="reference-rule",
                    confidence=round(min(conf, 1.0), 3),
                    evidence=evidence,
                    rationale=why,
                )
            )
    return out


def candidate_pairs(
    props: list[Proposition],
    existing: set[frozenset[str]],
    max_pairs: int,
) -> list[tuple[Proposition, Proposition]]:
    """Pairs of propositions that share an entity and are not already related."""
    by_entity: dict[str, list[Proposition]] = defaultdict(list)
    for p in props:
        for eid in {p.subject_entity_id, p.object_entity_id} - {None}:
            by_entity[eid].append(p)  # type: ignore[index]
    pairs: list[tuple[Proposition, Proposition]] = []
    seen: set[frozenset[str]] = set(existing)
    for group in by_entity.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                key = frozenset((a.proposition_id, b.proposition_id))
                if a.proposition_id == b.proposition_id or key in seen:
                    continue
                seen.add(key)
                pairs.append((a, b))
                if len(pairs) >= max_pairs:
                    return pairs
    return pairs


def classify_pairs(
    pairs: list[tuple[Proposition, Proposition]],
    classifier: PairClassifier,
    min_confidence: float = 0.6,
) -> list[Relation]:
    out: list[Relation] = []
    valid = {t.value for t in RelationType if t not in (RelationType.DUPLICATE_OF,)}
    for a, b in pairs:
        judgement = classifier.classify(a, b)
        if judgement is None:
            continue
        rel = (judgement.relation or "NONE").upper()
        if rel not in valid or judgement.confidence < min_confidence:
            continue
        src, dst = (a, b) if judgement.direction != "b_to_a" else (b, a)
        out.append(
            Relation(
                source_id=src.proposition_id,
                target_id=dst.proposition_id,
                relation_type=RelationType(rel),
                method=classifier.method,
                confidence=judgement.confidence,
                evidence=[a.source_quote, b.source_quote],
                rationale=judgement.rationale or None,
            )
        )
    return out
