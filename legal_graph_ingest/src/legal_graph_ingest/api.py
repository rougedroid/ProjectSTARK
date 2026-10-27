"""Public library API.

    from legal_graph_ingest import GraphIngestor

    with GraphIngestor(ollama_model="llama3.1:8b", neo4j_password="...") as g:
        report = g.ingest("contract.pdf")
        for p in g.propositions(report.document_id):
            print(p.normalized_text, p.modality.value)

Nothing here reads a .env file, configures logging, or touches the network until you call a method.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .config import Settings
from .export.json_export import build_snapshot, write_json
from .extraction.ollama_client import ChatBackend, OllamaExtractor, OllamaJudge
from .models.document import DocumentRecord
from .models.mention import Mention
from .models.proposition import Entity, Proposition
from .models.relation import Relation
from .pipeline import IngestPipeline, IngestReport
from .storage.memory import InMemoryRepository
from .storage.repository import Neo4jRepository, Repository

ProgressCallback = Callable[[int, int, str], None]  # (clause_number, total_clauses, clause_heading)


class GraphIngestor:
    """Facade over the whole pipeline: ingest PDFs, then read the graph back as Python objects.

    Args:
        settings: a `Settings`; defaults to `Settings.from_env(dotenv=None)` (environment variables only).
        repository: bring your own `Repository` implementation.
        in_memory: use an in-memory graph (no Neo4j needed). Ignored if `repository` is given.
        extractor / judge: bring your own (e.g. a subclass or test double).
        ollama_backend: any object with `.chat(model=, messages=, format=, options=)`; default is `ollama.Client`.
        init_schema: create Neo4j constraints on construction (idempotent).
        **overrides: any `Settings` field, e.g. `ollama_model="...", neo4j_password="..."`.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        repository: Optional[Repository] = None,
        in_memory: bool = False,
        extractor: Optional[OllamaExtractor] = None,
        judge: Optional[OllamaJudge] = None,
        ollama_backend: Optional[ChatBackend] = None,
        init_schema: bool = True,
        **overrides: Any,
    ) -> None:
        base = settings or Settings.from_env(dotenv=None)
        self.settings = dataclasses.replace(base, **overrides) if overrides else base
        self._extractor = extractor
        self._judge = judge
        self._backend = ollama_backend
        self._client = None

        if repository is not None:
            self.repository: Repository = repository
        elif in_memory:
            self.repository = InMemoryRepository()
        else:
            from .storage.neo4j_client import Neo4jClient

            self._client = Neo4jClient.from_settings(self.settings)
            self._client.verify()
            self.repository = Neo4jRepository(self._client)
        if init_schema:
            self.repository.init_schema()

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "GraphIngestor":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ pipeline
    def _pipeline(self, *, need_extractor: bool, llm: bool) -> IngestPipeline:
        extractor = self._extractor
        if extractor is None and need_extractor:
            extractor = self._extractor = OllamaExtractor(self.settings, self._backend)
        judge = self._judge
        if judge is None and llm:
            judge = self._judge = OllamaJudge(self.settings, self._backend)
        return IngestPipeline(self.settings, self.repository, extractor, judge)

    def ingest(
        self,
        pdf_path: str | Path,
        *,
        resolve: bool = True,
        llm_relations: bool = False,
        retry_quarantined: bool = False,
        max_clauses: Optional[int] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> IngestReport:
        """Extract (checkpointed, resumable) and by default resolve + relate a contract PDF."""
        return self._pipeline(need_extractor=True, llm=llm_relations).ingest(
            pdf_path,
            resolve=resolve,
            llm_relations=llm_relations,
            retry_quarantined=retry_quarantined,
            max_clauses=max_clauses,
            progress=progress,
        )

    def extract(
        self,
        pdf_path: str | Path,
        *,
        retry_quarantined: bool = False,
        max_clauses: Optional[int] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> IngestReport:
        """Extraction stage only."""
        return self._pipeline(need_extractor=True, llm=False).extract(
            pdf_path, retry_quarantined=retry_quarantined, max_clauses=max_clauses, progress=progress
        )

    def resolve(self, document_id: str, *, llm_relations: bool = False) -> IngestReport:
        """Resolution + relation pass on an already-extracted document."""
        return self._pipeline(need_extractor=False, llm=llm_relations).resolve(
            document_id, llm_relations=llm_relations
        )

    # ------------------------------------------------------------------ read the graph
    def document(self, document_id: str) -> Optional[DocumentRecord]:
        return self.repository.get_document(document_id)

    def propositions(self, document_id: str) -> list[Proposition]:
        """In document order. Each has `.source_quote`, `.mention_ids`, `.references` (with resolution state)."""
        return self.repository.load_propositions(document_id)

    def mentions(self, document_id: str) -> list[Mention]:
        return self.repository.load_mentions(document_id)

    def entities(self, document_id: str) -> list[Entity]:
        return self.repository.load_entities(document_id)

    def relations(self, document_id: str) -> list[Relation]:
        return self.repository.load_relations(document_id)

    def quarantined(self, document_id: str) -> list[dict]:
        return self.repository.load_quarantine(document_id)

    def snapshot(self, document_id: str) -> dict[str, Any]:
        """Whole graph as plain dicts (JSON-serialisable)."""
        return build_snapshot(self.repository, document_id)

    def export_json(self, document_id: str, path: str | Path) -> Path:
        return write_json(self.repository, document_id, path)


@dataclass
class IngestedDocument:
    """Everything about one ingested PDF, as plain Python objects (no database handle needed)."""
    report: IngestReport
    propositions: list[Proposition]
    mentions: list[Mention]
    entities: list[Entity]
    relations: list[Relation]
    quarantined: list[dict]

    @property
    def document_id(self) -> str:
        return self.report.document_id


def ingest_pdf(
    pdf_path: str | Path,
    *,
    resolve: bool = True,
    llm_relations: bool = False,
    retry_quarantined: bool = False,
    progress: Optional[ProgressCallback] = None,
    **ingestor_kwargs: Any,
) -> IngestedDocument:
    """One-call convenience: ingest a PDF and return the resulting graph as Python objects.

        doc = ingest_pdf("contract.pdf", in_memory=True, ollama_model="llama3.1:8b")
        for p in doc.propositions: ...

    `ingestor_kwargs` go to `GraphIngestor` (settings, in_memory, neo4j_*, ollama_*, ollama_backend, ...).
    """
    with GraphIngestor(**ingestor_kwargs) as g:
        report = g.ingest(
            pdf_path,
            resolve=resolve,
            llm_relations=llm_relations,
            retry_quarantined=retry_quarantined,
            progress=progress,
        )
        doc_id = report.document_id
        return IngestedDocument(
            report=report,
            propositions=g.propositions(doc_id),
            mentions=g.mentions(doc_id),
            entities=g.entities(doc_id),
            relations=g.relations(doc_id),
            quarantined=g.quarantined(doc_id),
        )
