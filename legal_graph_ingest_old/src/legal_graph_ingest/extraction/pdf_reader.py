"""Stage 1: read a PDF into canonical text plus page/layout metadata.

Text is built from PDF layout blocks: lines inside a block are joined with spaces, blocks
are separated by a blank line. That makes "paragraph" = "block", which the segmenter uses.
All offsets stored in the graph refer to the resulting `DocumentText.text`.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from ..models.document import DocumentText, PageSpan

_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?\s*$", re.IGNORECASE)


class PdfReadError(RuntimeError):
    pass


class ScannedPdfError(PdfReadError):
    """The PDF has (almost) no extractable text; OCR would be needed."""


def _open(path: Path):
    try:
        import pymupdf as fitz  # pymupdf >= 1.24.3
    except ImportError:  # pragma: no cover
        import fitz  # type: ignore
    return fitz.open(str(path))


def _clean_block(raw: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return re.sub(r"[ \t]+", " ", " ".join(lines)).strip()


def read_pdf(path: str | Path) -> DocumentText:
    path = Path(path)
    if not path.is_file():
        raise PdfReadError(f"PDF not found: {path}")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()

    doc = _open(path)
    try:
        pages_blocks: list[tuple[float, float, list[str]]] = []
        for page in doc:
            blocks = []
            for b in page.get_text("blocks", sort=True):
                # (x0, y0, x1, y1, text, block_no, block_type); type 0 = text
                if len(b) >= 7 and b[6] != 0:
                    continue
                text = _clean_block(b[4])
                if text and not _PAGE_NUMBER.match(text):
                    blocks.append(text)
            pages_blocks.append((page.rect.width, page.rect.height, blocks))
        page_count = len(pages_blocks)
    finally:
        doc.close()

    # Drop running headers/footers: identical blocks on most pages.
    if page_count >= 3:
        counts = Counter(b for _, _, bl in pages_blocks for b in set(bl))
        repeated = {b for b, n in counts.items() if n >= max(3, int(0.6 * page_count)) and len(b) < 120}
        pages_blocks = [(w, h, [b for b in bl if b not in repeated]) for w, h, bl in pages_blocks]

    parts: list[str] = []
    spans: list[PageSpan] = []
    cursor = 0
    for i, (w, h, bl) in enumerate(pages_blocks, start=1):
        page_text = "\n\n".join(bl)
        if parts:
            cursor += 2  # the "\n\n" separator between pages
        spans.append(PageSpan(page=i, start=cursor, end=cursor + len(page_text), width=w, height=h, blocks=len(bl)))
        parts.append(page_text)
        cursor += len(page_text)
    text = "\n\n".join(parts)

    if len(text.strip()) < 20 * max(page_count, 1):
        raise ScannedPdfError(
            "Very little extractable text found; the PDF looks scanned. Add an OCR step "
            "(e.g. ocrmypdf) before ingesting."
        )
    return DocumentText(filename=path.name, sha256=sha, page_count=page_count, text=text, pages=spans)
