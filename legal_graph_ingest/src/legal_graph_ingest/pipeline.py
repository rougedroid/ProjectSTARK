"""Orchestrates the stages. Extraction -> (checkpointed persistence) -> resolution -> relations.

Boundary: extraction records what the document says; resolution identifies what references mean;
relation analysis determines how propositions connect. Semantic relations are only generated
after every clause has been extracted (or quarantined).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import Settings
from .extraction.context import ContextBuilder, ContextMemory, find_defined_terms
from .extraction.ollama_client import ExtractionFailure, OllamaExtractor, OllamaJudge
from .extraction.pdf_reader import read_pdf
from .extraction.segmenter import Clause, segment
from .ids import normalize_key, stable_id
from .models.document import DocumentRecord, DocumentText, IngestionStatus
from .models.mention import Mention
from .models.proposition import Entity, ExtractedProposition, Proposition
from .models.relation import Relation
from .resolution.coreference import resolve_references
from .resolution.duplicates import find_duplicates
from .resolution.entities import make_entity
from .resolution.relations import candidate_pairs, classify_pairs, derive_structural_relations
from .storage.repository import CHECKPOINT_DONE, CHECKPOINT_QUARANTINED, ClauseBatch, Repository
from .validation.evidence import locate_quote
from .validation.references import LOCAL_PREFIX, validate_references
from .validation.schema import ValidationFailure, parse_extraction

log = logging.getLogger(__name__)

Validated = list[tuple[ExtractedProposition, tuple[int, int]]]


@dataclass
class IngestReport:
    document_id: str
    clauses_total: int = 0
    clauses_extracted: int = 0
    clauses_skipped: int = 0
    clauses_quarantined: int = 0
    propositions: int = 0
    relations: int = 0
    unresolved_references: int = 0
    status: str = IngestionStatus.PENDING

    def summary(self) -> str:
        return (
            f"document={self.document_id} status={self.status} clauses={self.clauses_total} "
            f"(extracted={self.clauses_extracted}, skipped={self.clauses_skipped}, "
            f"quarantined={self.clauses_quarantined}) propositions={self.propositions} "
            f"relations={self.relations} unresolved_refs={self.unresolved_references}"
        )


class IngestPipeline:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        extractor: Optional[OllamaExtractor] = None,
        judge: Optional[OllamaJudge] = None,
    ):
        self.settings = settings
        self.repo = repo
        self.extractor = extractor
        self.judge = judge  # optional: LLM pair classification + reference adjudication
        self.context_builder = ContextBuilder()

    # ------------------------------------------------------------------ extraction
    def extract(
        self,
        pdf_path: str | Path,
        retry_quarantined: bool = False,
        max_clauses: Optional[int] = None,
        progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> IngestReport:
        if self.extractor is None:
            raise RuntimeError("An extractor is required for ingestion.")
        doc = read_pdf(pdf_path)
        document_id = stable_id("doc", doc.sha256)
        self.repo.upsert_document(
            DocumentRecord(document_id, doc.filename, doc.sha256, doc.page_count, IngestionStatus.EXTRACTING)
        )
        self.repo.set_status(document_id, IngestionStatus.EXTRACTING)

        clauses = segment(doc.text, self.settings.max_clause_chars)
        report = IngestReport(document_id=document_id, clauses_total=len(clauses), status=IngestionStatus.EXTRACTING)
        log.info("%s: %d pages, %d clauses", doc.filename, doc.page_count, len(clauses))

        memory = self._seed_memory(document_id, doc)
        previous: Optional[Clause] = None
        for n, clause in enumerate(clauses, start=1):
            if progress:
                progress(n, len(clauses), clause.heading)
            status = self.repo.clause_status(document_id, clause.key)
            if status == CHECKPOINT_DONE or (status == CHECKPOINT_QUARANTINED and not retry_quarantined):
                report.clauses_skipped += 1
                previous = clause
                continue
            if max_clauses is not None and report.clauses_extracted + report.clauses_quarantined >= max_clauses:
                break

            ctx = self.context_builder.build(clause, memory, previous)
            try:
                validated = self.extractor.extract(
                    ctx, lambda raw, c=clause, k=memory: self._validate(raw, doc, c, k)
                )
            except ExtractionFailure as exc:
                log.error("clause %s quarantined: %s", clause.key, exc)
                self.repo.quarantine_clause(document_id, clause.key, str(exc), exc.raw)
                report.clauses_quarantined += 1
                previous = clause
                continue

            batch = self._build_batch(document_id, doc, clause, validated, memory)
            self.repo.save_clause(document_id, batch)  # clause + checkpoint, one transaction
            for p in batch.propositions:
                memory.add_proposition(p.proposition_id, p.normalized_text, clause.heading)
            for e in batch.entities:
                memory.add_entity(e.canonical_name)
            report.clauses_extracted += 1
            report.propositions += len(batch.propositions)
            previous = clause
            log.info("clause %d/%d %s: %d propositions", n, len(clauses), clause.heading, len(batch.propositions))

        counts = self.repo.count_clauses(document_id)
        finished = counts.get(CHECKPOINT_DONE, 0) + counts.get(CHECKPOINT_QUARANTINED, 0) >= len(clauses)
        report.status = IngestionStatus.EXTRACTED if finished else IngestionStatus.EXTRACTING
        self.repo.set_status(document_id, report.status)
        return report

    def _seed_memory(self, document_id: str, doc: DocumentText) -> ContextMemory:
        memory = ContextMemory()
        memory.add_defined_terms(find_defined_terms(doc.text))
        # resume support: rebuild context from what is already persisted
        for e in self.repo.load_entities(document_id):
            memory.add_entity(e.canonical_name)
        for p in self.repo.load_propositions(document_id):
            memory.add_proposition(p.proposition_id, p.normalized_text)
        return memory

    def _validate(self, raw: str, doc: DocumentText, clause: Clause, memory: ContextMemory) -> Validated:
        result = parse_extraction(raw)
        errors: list[str] = []
        validated: Validated = []
        for ep in result.propositions:
            span = locate_quote(ep.source_quote, doc.text, clause.start, clause.end)
            if span is None:
                errors.append(f"{ep.local_id}: source_quote is not a verbatim excerpt of the CLAUSE TEXT: {ep.source_quote[:100]!r}")
            else:
                validated.append((ep, span))
        known = {a.id for a in memory.propositions}
        errors += validate_references(result.propositions, known)
        if errors:
            raise ValidationFailure("; ".join(errors), raw)
        return validated

    def _build_batch(
        self, document_id: str, doc: DocumentText, clause: Clause, validated: Validated, memory: ContextMemory
    ) -> ClauseBatch:
        mentions: dict[str, Mention] = {}
        entities: dict[str, Entity] = {}
        local_to_global: dict[str, str] = {}
        staged: list[tuple[ExtractedProposition, str, str]] = []

        for ep, (s, e) in validated:
            mid = stable_id("men", document_id, s, e)
            if mid not in mentions:
                p0, p1 = doc.pages_for_span(s, e)
                mentions[mid] = Mention(
                    mention_id=mid,
                    document_id=document_id,
                    page_start=p0,
                    page_end=p1,
                    section=clause.section,
                    clause_number=clause.clause_number,
                    start_offset=s,
                    end_offset=e,
                    source_text=doc.text[s:e],
                )
            pid = stable_id("prop", document_id, s, e, normalize_key(ep.normalized_text))
            local_to_global[ep.local_id] = pid
            staged.append((ep, pid, mid))

        props: list[Proposition] = []
        seen: set[str] = set()
        for ep, pid, mid in staged:
            if pid in seen:
                continue
            seen.add(pid)
            data = ep.model_dump()
            for ref in data["references"]:
                ref["candidate_ids"] = [
                    local_to_global.get(c[len(LOCAL_PREFIX):], c) if c.startswith(LOCAL_PREFIX) else c
                    for c in ref["candidate_ids"]
                ]
                if not ref["candidate_ids"] and ref["kind"] in ("pronoun", "anaphoric_phrase"):
                    ref["candidate_ids"] = self._candidate_antecedents(ep, pid, staged, memory)
            subj = make_entity(document_id, ep.subject, memory.defined_terms)
            obj = make_entity(document_id, ep.object, memory.defined_terms)
            for ent in (subj, obj):
                if ent:
                    cur = entities.get(ent.entity_id)
                    if cur:
                        cur.aliases = list(dict.fromkeys(cur.aliases + ent.aliases))
                    else:
                        entities[ent.entity_id] = ent
            props.append(
                Proposition(
                    **data,
                    proposition_id=pid,
                    document_id=document_id,
                    clause_key=clause.key,
                    mention_ids=[mid],
                    subject_entity_id=subj.entity_id if subj else None,
                    object_entity_id=obj.entity_id if obj else None,
                )
            )
        return ClauseBatch(clause.key, list(mentions.values()), props, list(entities.values()))

    @staticmethod
    def _candidate_antecedents(
        ep: ExtractedProposition, pid: str, staged: list[tuple[ExtractedProposition, str, str]], memory: ContextMemory
    ) -> list[str]:
        """Record plausible antecedents for an anaphor the model left without candidates.

        This only *records candidates*; coreference resolution still refuses to pick between several.
        """
        earlier_in_clause: list[str] = []
        for other, other_pid, _ in staged:
            if other_pid == pid:
                break
            earlier_in_clause.append(other_pid)
        if earlier_in_clause:
            return earlier_in_clause
        return [a.id for a in memory.propositions[-3:]]

    # ------------------------------------------------------------------ resolution
    def resolve(self, document_id: str, llm_relations: bool = False) -> IngestReport:
        doc = self.repo.get_document(document_id)
        if doc is None:
            raise KeyError(f"unknown document_id: {document_id}")
        if doc.ingestion_status not in (IngestionStatus.EXTRACTED, IngestionStatus.RESOLVED):
            raise RuntimeError(
                f"document is '{doc.ingestion_status}': relations are only generated after extraction has "
                "completed for every clause. Re-run ingestion to finish extraction."
            )
        props = self.repo.load_propositions(document_id)

        adjudicator = None
        if self.judge is not None:
            judge = self.judge

            def adjudicator(prop, ref, candidates):  # noqa: F811
                v = judge.adjudicate(prop, ref, candidates)
                return (v.chosen_id, v.confidence, judge.method) if v else None

        relations: list[Relation] = []
        relations += resolve_references(props, adjudicator)               # 7a coreference
        relations += find_duplicates(props, self.settings.duplicate_threshold)  # 7b duplicates
        relations += derive_structural_relations(props)                  # 8 rule-based relations

        if llm_relations:
            if self.judge is None:
                raise RuntimeError("llm_relations requires an OllamaJudge.")
            existing = {frozenset((r.source_id, r.target_id)) for r in relations}
            pairs = candidate_pairs(props, existing, self.settings.max_llm_relation_pairs)
            relations += classify_pairs(pairs, self.judge, self.settings.min_relation_confidence)

        self.repo.save_resolution(document_id, props, relations)
        self.repo.set_status(document_id, IngestionStatus.RESOLVED)
        unresolved = sum(1 for p in props for r in p.references if not r.resolved_id)
        return IngestReport(
            document_id=document_id,
            propositions=len(props),
            relations=len(relations),
            unresolved_references=unresolved,
            status=IngestionStatus.RESOLVED,
        )

    # ------------------------------------------------------------------ all stages
    def ingest(
        self,
        pdf_path: str | Path,
        resolve: bool = True,
        llm_relations: bool = False,
        retry_quarantined: bool = False,
        max_clauses: Optional[int] = None,
        progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> IngestReport:
        report = self.extract(pdf_path, retry_quarantined=retry_quarantined, max_clauses=max_clauses, progress=progress)
        if resolve and report.status == IngestionStatus.EXTRACTED:
            r = self.resolve(report.document_id, llm_relations=llm_relations)
            report.relations, report.unresolved_references, report.status = r.relations, r.unresolved_references, r.status
            report.propositions = r.propositions
        return report
