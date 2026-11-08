"""Stage 5c: reference hygiene. Unknown antecedents are dropped, never invented."""
from __future__ import annotations

import logging

from ..models.proposition import ExtractedProposition

log = logging.getLogger(__name__)
LOCAL_PREFIX = "local:"


def validate_references(
    props: list[ExtractedProposition],
    known_ids: set[str],
) -> list[str]:
    """Filter each reference's candidate_ids to ids we can actually resolve.

    Returns hard errors (self-references). Unknown candidate ids are dropped with a warning; the
    reference itself is kept (unresolved) so the later resolution stage can decide.
    """
    local_ids = {p.local_id for p in props}
    errors: list[str] = []
    for p in props:
        for ref in p.references:
            kept: list[str] = []
            for cid in ref.candidate_ids:
                bare = cid[len(LOCAL_PREFIX):] if cid.startswith(LOCAL_PREFIX) else cid
                if bare == p.local_id:
                    errors.append(f"{p.local_id}: reference {ref.surface_text!r} points at itself")
                elif cid.startswith(LOCAL_PREFIX) and bare in local_ids:
                    kept.append(cid)
                elif bare in local_ids:
                    kept.append(LOCAL_PREFIX + bare)
                elif cid in known_ids:
                    kept.append(cid)
                else:
                    log.warning("dropping unknown candidate id %r for reference %r", cid, ref.surface_text)
            ref.candidate_ids = list(dict.fromkeys(kept))
    return errors
