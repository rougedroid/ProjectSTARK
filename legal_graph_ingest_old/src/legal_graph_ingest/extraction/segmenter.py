"""Stage 2: split document text into clauses, paragraphs and sentences (all with offsets)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str


@dataclass
class Clause:
    key: str
    section: Optional[str]
    clause_number: Optional[str]
    start: int
    end: int
    text: str
    paragraphs: list[Span] = field(default_factory=list)
    sentences: list[Span] = field(default_factory=list)

    @property
    def heading(self) -> str:
        parts = [p for p in (self.section, self.clause_number) if p]
        return " / ".join(parts) if parts else "(preamble)"


_NUMBERED = re.compile(
    r"^(?:(?:Article|ARTICLE|Section|SECTION|Clause|CLAUSE)\s+)?(\d+(?:\.\d+)*)[.)]?\s+(\S.*)$",
    re.DOTALL,
)
_PARA_SPLIT = re.compile(r"\n\s*\n")
_SENT_END = re.compile(r"[.!?][\"\u201d\u2019)]*\s+(?=[A-Z0-9\u201c\"(])")
_ABBREVIATIONS = {
    "inc", "ltd", "co", "no", "nos", "mr", "mrs", "ms", "dr", "vs", "etc", "corp",
    "llc", "art", "sec", "cl", "e.g", "i.e", "approx", "para", "pp", "st",
}


def paragraph_spans(text: str, base: int = 0) -> list[Span]:
    spans: list[Span] = []
    pos = 0
    for m in list(_PARA_SPLIT.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        chunk = text[pos:end]
        if chunk.strip():
            lead = len(chunk) - len(chunk.lstrip())
            s, e = pos + lead, pos + len(chunk.rstrip())
            spans.append(Span(base + s, base + e, text[s:e]))
        pos = m.end() if m else len(text)
    return spans


def sentence_spans(text: str, base: int = 0) -> list[Span]:
    spans: list[Span] = []
    start = 0
    for m in _SENT_END.finditer(text):
        before = text[start:m.start()].split()
        last = before[-1].lower().rstrip(".") if before else ""
        if last in _ABBREVIATIONS:
            continue
        end = m.start() + len(m.group(0).rstrip())  # includes a closing quote/paren if present
        spans.append(Span(base + start, base + end, text[start:end]))
        start = m.end()
    if text[start:].strip():
        tail = text[start:]
        s = start + (len(tail) - len(tail.lstrip()))
        e = start + len(tail.rstrip())
        spans.append(Span(base + s, base + e, text[s:e]))
    return spans


def _is_section_heading(number: str, rest: str) -> bool:
    return "." not in number and len(rest) <= 80 and not rest.rstrip().endswith((".", ";", ":", ","))


def segment(text: str, max_chars: int = 3500) -> list[Clause]:
    """Group paragraphs into clauses at numbered headings, then split oversized clauses."""
    paras = paragraph_spans(text)
    groups: list[dict] = []
    section: Optional[str] = None
    current: dict = {"number": None, "section": None, "paras": []}

    for p in paras:
        m = _NUMBERED.match(p.text)
        if m and m.group(2)[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ(\u201c\"":
            number, rest = m.group(1), m.group(2)
            if _is_section_heading(number, rest):
                section = f"{number} {rest.strip()}"
                groups.append(current)
                current = {"number": number, "section": section, "paras": []}
                continue
            groups.append(current)
            current = {"number": number, "section": section, "paras": [p]}
            continue
        current["paras"].append(p)
    groups.append(current)

    clauses: list[Clause] = []
    for g in groups:
        if not g["paras"]:
            continue
        for chunk in _chunk_paragraphs(g["paras"], max_chars):
            start, end = chunk[0].start, chunk[-1].end
            body = text[start:end]
            sentences = [s for p in chunk for s in sentence_spans(p.text, p.start)]
            clauses.append(
                Clause(
                    key=f"c{start:08d}",
                    section=g["section"],
                    clause_number=g["number"],
                    start=start,
                    end=end,
                    text=body,
                    paragraphs=list(chunk),
                    sentences=sentences,
                )
            )
    return clauses


def _chunk_paragraphs(paras: list[Span], max_chars: int) -> list[list[Span]]:
    chunks: list[list[Span]] = []
    cur: list[Span] = []
    size = 0
    for p in paras:
        plen = p.end - p.start
        if cur and size + plen > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += plen
    if cur:
        chunks.append(cur)
    return chunks
