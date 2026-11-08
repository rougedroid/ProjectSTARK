"""Stage 7b: identify duplicate propositions without merging or rewriting anything."""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

from ..ids import normalize_key
from ..models.proposition import Proposition
from ..models.relation import Relation, RelationType


def find_duplicates(props: list[Proposition], threshold: float = 0.92) -> list[Relation]:
    """Later proposition -[:DUPLICATE_OF]-> earlier one. `props` must be in document order."""
    buckets: dict[tuple, list[Proposition]] = defaultdict(list)
    for p in props:
        buckets[(p.modality, p.polarity, normalize_key(p.subject))].append(p)

    relations: list[Relation] = []
    for bucket in buckets.values():
        for i, later in enumerate(bucket):
            for earlier in bucket[:i]:
                if later.proposition_id == earlier.proposition_id:
                    continue
                a, b = normalize_key(earlier.normalized_text), normalize_key(later.normalized_text)
                ratio = 1.0 if a == b else SequenceMatcher(None, a, b).ratio()
                if ratio >= threshold:
                    relations.append(
                        Relation(
                            source_id=later.proposition_id,
                            target_id=earlier.proposition_id,
                            relation_type=RelationType.DUPLICATE_OF,
                            method="normalized-text-similarity",
                            confidence=round(ratio, 4),
                            evidence=[earlier.source_quote, later.source_quote],
                            rationale=f"same modality/polarity/subject; text similarity {ratio:.2f}",
                        )
                    )
                    break  # link each proposition to its earliest duplicate only
    return relations
