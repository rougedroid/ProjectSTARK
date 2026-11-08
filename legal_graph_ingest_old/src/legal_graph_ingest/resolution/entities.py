"""Canonical entities. Created conservatively: unclear subjects/objects stay entity-less."""
from __future__ import annotations

import re
from typing import Optional

from ..ids import normalize_key, stable_id
from ..models.proposition import Entity

_ARTICLES = ("the ", "a ", "an ", "each ", "any ", "such ", "this ", "that ")
_CONNECTORS = {"of", "and", "the", "for", "&", "de", "von"}
_PRONOUNS = {"it", "they", "them", "he", "she", "which", "who", "that", "this", "these", "those", "its", "their", "such"}
_PARTY_WORDS = {
    "supplier", "buyer", "seller", "purchaser", "customer", "client", "vendor", "licensor", "licensee",
    "contractor", "company", "party", "parties", "landlord", "tenant", "lender", "borrower", "employer",
    "employee", "consultant", "provider", "recipient", "discloser", "assignor", "assignee",
}
_ORG_SUFFIX = re.compile(r"\b(inc|ltd|llc|llp|gmbh|corp|corporation|limited|plc|pvt|co)\.?$", re.IGNORECASE)
_DOC_WORDS = {"agreement", "contract", "schedule", "annex", "exhibit", "appendix", "policy", "notice"}


def strip_article(name: str) -> str:
    n = name.strip().strip(".,;:")
    low = n.lower()
    for art in _ARTICLES:
        if low.startswith(art):
            return n[len(art):].strip()
    return n


def is_entity_like(name: str, defined_terms: list[str]) -> bool:
    core = strip_article(name)
    if not core or len(core.split()) > 6:
        return False
    if core.lower() in _PRONOUNS:
        return False
    if core in defined_terms:
        return True
    for w in core.split():
        if w.lower() in _CONNECTORS:
            continue
        if not (w[0].isupper() or w[0].isdigit()):
            return False
    return True


def guess_type(name: str, defined_terms: list[str]) -> str:
    low = name.lower()
    if _ORG_SUFFIX.search(name):
        return "organization"
    last = low.split()[-1] if low.split() else ""
    if low in _PARTY_WORDS or last in _PARTY_WORDS:
        return "party"
    if last in _DOC_WORDS:
        return "document"
    if name in defined_terms:
        return "defined_term"
    return "other"


def make_entity(document_id: str, surface: Optional[str], defined_terms: list[str]) -> Optional[Entity]:
    if not surface or not is_entity_like(surface, defined_terms):
        return None
    canonical = strip_article(surface)
    key = normalize_key(canonical)
    if not key:
        return None
    aliases = [surface.strip()] if surface.strip() != canonical else []
    return Entity(
        entity_id=stable_id("ent", document_id, key),
        document_id=document_id,
        canonical_name=canonical,
        entity_type=guess_type(canonical, defined_terms),
        aliases=aliases,
    )
