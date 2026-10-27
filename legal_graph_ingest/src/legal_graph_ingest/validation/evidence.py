"""Stage 5b: every proposition must be traceable to exact text in the PDF."""
from __future__ import annotations

from typing import Optional

MIN_QUOTE_CHARS = 8
_TRANS = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "}
)


def _normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs and unify typographic quotes/dashes, keeping an index map."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(text.translate(_TRANS)):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            prev_space = True
        else:
            out.append(ch)
            prev_space = False
        idx.append(i)
    return "".join(out), idx


def locate_quote(quote: str, text: str, start: int = 0, end: Optional[int] = None) -> Optional[tuple[int, int]]:
    """Return absolute (start, end) offsets of `quote` inside text[start:end], or None.

    Tries an exact match first, then a whitespace/typography-insensitive match, then case-insensitive.
    """
    end = len(text) if end is None else end
    window = text[start:end]
    q = quote.strip()
    if len(q) < MIN_QUOTE_CHARS:
        return None
    i = window.find(q)
    if i >= 0:
        return start + i, start + i + len(q)

    nw, widx = _normalize(window)
    nq, _ = _normalize(q)
    nq = nq.strip()
    if not nq:
        return None
    for hay, needle in ((nw, nq), (nw.lower(), nq.lower())):
        if len(hay) != len(nw):
            continue
        j = hay.find(needle)
        if j >= 0:
            return start + widx[j], start + widx[j + len(needle) - 1] + 1
    return None
