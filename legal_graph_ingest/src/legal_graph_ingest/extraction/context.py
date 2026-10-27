"""Stage 3: build context windows so the extractor can see what a passage refers back to."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .segmenter import Clause

_DEFINED = [
    re.compile(r"[\u201c\"]([A-Z][\w\-& ]{1,60}?)[\u201d\"]\s+(?:shall\s+)?(?:means?|has the meaning|refers? to)"),
    re.compile(r"\((?:the\s+|each,?\s+a\s+|together,?\s+the\s+)?[\u201c\"]([A-Z][\w\-& ]{1,60}?)[\u201d\"]\)"),
    re.compile(r",\s+(?:the\s+)?[\u201c\"]([A-Z][\w\-& ]{1,60}?)[\u201d\"][,)]"),
]


def find_defined_terms(text: str) -> list[str]:
    found: dict[str, None] = {}
    for pat in _DEFINED:
        for m in pat.finditer(text):
            found[m.group(1).strip()] = None
    return list(found)


@dataclass
class Antecedent:
    id: str
    text: str
    clause_heading: str = ""


@dataclass
class ContextMemory:
    """Running state of what has been extracted so far (propositions, entities, defined terms)."""
    defined_terms: list[str] = field(default_factory=list)
    entity_names: list[str] = field(default_factory=list)
    propositions: list[Antecedent] = field(default_factory=list)

    def add_defined_terms(self, terms: list[str]) -> None:
        for t in terms:
            if t not in self.defined_terms:
                self.defined_terms.append(t)

    def add_entity(self, name: str) -> None:
        if name and name not in self.entity_names:
            self.entity_names.append(name)

    def add_proposition(self, prop_id: str, text: str, clause_heading: str = "") -> None:
        if all(a.id != prop_id for a in self.propositions):
            self.propositions.append(Antecedent(prop_id, text, clause_heading))


@dataclass
class ExtractionContext:
    clause: Clause
    preceding_text: str
    antecedents: list[Antecedent]
    entity_names: list[str]
    defined_terms: list[str]

    def render(self) -> str:
        c = self.clause
        out: list[str] = [f"HEADING: {c.heading}"]
        if self.defined_terms:
            out.append("DEFINED TERMS: " + "; ".join(self.defined_terms))
        if self.entity_names:
            out.append("KNOWN ENTITIES: " + "; ".join(self.entity_names))
        if self.preceding_text:
            out.append("PRECEDING PARAGRAPH (context only, do not extract from it):\n" + self.preceding_text)
        if self.antecedents:
            out.append(
                "EARLIER PROPOSITIONS (candidate antecedents; cite these ids in references[].candidate_ids):\n"
                + "\n".join(f"- {a.id}: {a.text}" for a in self.antecedents)
            )
        numbered = "\n".join(f"[S{i}] {s.text}" for i, s in enumerate(c.sentences, start=1))
        out.append("CLAUSE TEXT (extract from this only; source_quote must be copied verbatim from it):\n" + c.text)
        out.append("SENTENCES:\n" + numbered)
        return "\n\n".join(out)


class ContextBuilder:
    def __init__(self, max_antecedents: int = 8, max_entities: int = 60, max_preceding_chars: int = 800):
        self.max_antecedents = max_antecedents
        self.max_entities = max_entities
        self.max_preceding_chars = max_preceding_chars

    def build(
        self,
        clause: Clause,
        memory: ContextMemory,
        previous_clause: Optional[Clause] = None,
    ) -> ExtractionContext:
        preceding = ""
        if previous_clause and previous_clause.paragraphs:
            preceding = previous_clause.paragraphs[-1].text[-self.max_preceding_chars:]
        return ExtractionContext(
            clause=clause,
            preceding_text=preceding,
            antecedents=memory.propositions[-self.max_antecedents:],
            entity_names=memory.entity_names[-self.max_entities:],
            defined_terms=list(memory.defined_terms),
        )
