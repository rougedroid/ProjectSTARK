"""Command line interface."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

from .config import ConfigError, Settings
from .export.json_export import write_json
from .extraction.ollama_client import OllamaExtractor, OllamaJudge
from .pipeline import IngestPipeline
from .storage.memory import InMemoryRepository
from .storage.neo4j_client import Neo4jClient
from .storage.repository import Neo4jRepository, Repository


def _repo(settings: Settings, dry_run: bool) -> tuple[Repository, Optional[Neo4jClient]]:
    if dry_run:
        return InMemoryRepository(), None
    client = Neo4jClient.from_settings(settings)
    client.verify()
    return Neo4jRepository(client), client


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="legal-graph-ingest", description="Contract PDF -> proposition graph in Neo4j")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--env-file", default=".env")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-schema", help="create Neo4j constraints and indexes")

    ing = sub.add_parser("ingest", help="extract (and by default resolve) a contract PDF")
    ing.add_argument("pdf")
    ing.add_argument("--no-resolve", action="store_true", help="stop after extraction")
    ing.add_argument("--llm-relations", action="store_true", help="also classify entity-sharing pairs with the LLM")
    ing.add_argument("--retry-quarantined", action="store_true")
    ing.add_argument("--max-clauses", type=int, default=None, help="process at most N new clauses (for testing/resume)")
    ing.add_argument("--export", metavar="PATH", help="write a JSON snapshot when done")
    ing.add_argument("--dry-run", action="store_true", help="use an in-memory graph instead of Neo4j")

    res = sub.add_parser("resolve", help="run the resolution pass on an already-extracted document")
    res.add_argument("document_id")
    res.add_argument("--llm-relations", action="store_true")
    res.add_argument("--export", metavar="PATH")

    exp = sub.add_parser("export", help="export a document's graph to JSON")
    exp.add_argument("document_id")
    exp.add_argument("path")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = Settings.from_env(args.env_file)
        dry = getattr(args, "dry_run", False)
        repo, client = _repo(settings, dry)
        try:
            if args.command == "init-schema":
                repo.init_schema()
                print("schema ready")
                return 0

            if args.command == "export":
                print(write_json(repo, args.document_id, args.path))
                return 0

            need_llm = args.command == "ingest" or getattr(args, "llm_relations", False)
            judge = None
            extractor = None
            if need_llm:
                extractor = OllamaExtractor(settings) if args.command == "ingest" else None
                if getattr(args, "llm_relations", False):
                    judge = OllamaJudge(settings)
            pipeline = IngestPipeline(settings, repo, extractor, judge)

            if args.command == "ingest":
                repo.init_schema()
                report = pipeline.ingest(
                    args.pdf,
                    resolve=not args.no_resolve,
                    llm_relations=args.llm_relations,
                    retry_quarantined=args.retry_quarantined,
                    max_clauses=args.max_clauses,
                )
            else:
                report = pipeline.resolve(args.document_id, llm_relations=args.llm_relations)

            print(report.summary())
            if getattr(args, "export", None):
                print(write_json(repo, report.document_id, args.export))
            return 0
        finally:
            if client:
                client.close()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # surface a clean message; -v shows the traceback
        if args.verbose:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
