from __future__ import annotations

import bisect
from dataclasses import dataclass, field


class IngestionStatus:
    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class PageSpan:
    """Character range of one page inside DocumentText.text (1-based page number)."""
    page: int
    start: int
    end: int
    width: float = 0.0
    height: float = 0.0
    blocks: int = 0


@dataclass
class DocumentText:
    """The canonical text of the PDF. All offsets in the graph refer to `text`."""
    filename: str
    sha256: str
    page_count: int
    text: str
    pages: list[PageSpan] = field(default_factory=list)

    def page_for_offset(self, offset: int) -> int:
        if not self.pages:
            return 1
        starts = [p.start for p in self.pages]
        i = bisect.bisect_right(starts, offset) - 1
        return self.pages[max(i, 0)].page

    def pages_for_span(self, start: int, end: int) -> tuple[int, int]:
        return self.page_for_offset(start), self.page_for_offset(max(start, end - 1))


@dataclass
class DocumentRecord:
    document_id: str
    filename: str
    sha256: str
    page_count: int
    ingestion_status: str = IngestionStatus.PENDING

    def to_node_props(self) -> dict:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "ingestion_status": self.ingestion_status,
        }

    @classmethod
    def from_node_props(cls, p: dict) -> "DocumentRecord":
        return cls(
            document_id=p["document_id"],
            filename=p.get("filename", ""),
            sha256=p.get("sha256", ""),
            page_count=int(p.get("page_count", 0)),
            ingestion_status=p.get("ingestion_status", IngestionStatus.PENDING),
        )
