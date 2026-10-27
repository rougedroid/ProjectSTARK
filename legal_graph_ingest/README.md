# legal_graph_ingest

Turns a **contract PDF** into a **source-grounded proposition graph** in Neo4j.
It does **not** perform legal reasoning. Boundary between stages:

> extraction records *what the document says* → resolution identifies *what its references mean* →
> relation analysis determines *how its propositions connect*.

Ollama **proposes** structured extractions · Python **validates and persists** · Neo4j **stores**.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # fill in OLLAMA_MODEL and NEO4J_PASSWORD
ollama pull <your-model>    # any model that supports structured outputs
```

## Use as a library (main use case)

Install into your project (from the unzipped folder, or build a wheel with `python -m build`):

```bash
pip install /path/to/legal_graph_ingest          # or: pip install -e /path/to/legal_graph_ingest
```

```python
from legal_graph_ingest import GraphIngestor, ingest_pdf

# One call, no database: get the graph back as Python objects
doc = ingest_pdf("contract.pdf", in_memory=True, ollama_model="llama3.1:8b")
for p in doc.propositions:
    print(p.modality.value, p.normalized_text, "<-", p.source_quote)

# Persist in Neo4j, query later
with GraphIngestor(ollama_model="llama3.1:8b", neo4j_password="...") as g:
    report = g.ingest("contract.pdf", progress=lambda n, total, head: print(n, total, head))
    props = g.propositions(report.document_id)       # list[Proposition]
    rels = g.relations(report.document_id)           # list[Relation] (evidence, method, confidence)
    g.export_json(report.document_id, "graph.json")
```

`GraphIngestor` methods: `ingest`, `extract`, `resolve`, `document`, `propositions`, `mentions`,
`entities`, `relations`, `quarantined`, `snapshot`, `export_json`, `close`.

Library behaviour: no `.env` is read (environment variables and keyword arguments only), no logging
is configured (use the standard `logging` module on the `legal_graph_ingest` logger), and nothing
connects to Ollama or Neo4j until you call a method. Reading an existing graph needs no Ollama model.
Pass `settings=Settings(...)`, any `Settings` field as a keyword, your own `repository=`, or an
`ollama_backend=` (anything with `.chat(model=, messages=, format=, options=)`) to customise.
See `examples/use_as_library.py`.

## Use (command line)

```bash
legal-graph-ingest init-schema                                  # constraints + indexes (also run by ingest)
legal-graph-ingest ingest contract.pdf --export exports/c.json  # extract -> resolve -> export
legal-graph-ingest ingest contract.pdf --no-resolve             # extraction only
legal-graph-ingest resolve <document_id> [--llm-relations]      # second pass on an extracted document
legal-graph-ingest export <document_id> out.json
legal-graph-ingest ingest contract.pdf --dry-run --export out.json   # no Neo4j needed (in-memory graph)
```

Useful flags: `--max-clauses N` (process N new clauses then stop; run again to resume),
`--retry-quarantined`, `--llm-relations` (LLM classification of entity-sharing proposition pairs
plus adjudication of ambiguous references), `-v`.

`python -m legal_graph_ingest ...` works too.

## Pipeline

| # | Stage | Module | Output |
|---|-------|--------|--------|
| 1 | Read PDF | `extraction/pdf_reader.py` | canonical text, page spans, layout metadata |
| 2 | Segment | `extraction/segmenter.py` | clauses, paragraphs, sentences (all with offsets) |
| 3 | Build context | `extraction/context.py` | heading, preceding paragraph, defined terms, entities, antecedent ids |
| 4 | Extract | `extraction/ollama_client.py` | structured propositions (Pydantic schema as Ollama `format`) |
| 5 | Validate | `validation/*` | schema check, verbatim `source_quote` located in the PDF text, reference hygiene |
| 6 | Persist | `storage/repository.py` | Document / Mention / Proposition / Entity + checkpoint, **one transaction per clause** |
| 7 | Resolve | `resolution/coreference.py`, `duplicates.py` | reference links, duplicate candidates |
| 8 | Relate | `resolution/relations.py` | SUPPORTS / CONTRADICTS / QUALIFIES / EXCEPTS_FROM (+ REFERS_TO, DUPLICATE_OF) |
| 9 | Export | `export/json_export.py` | JSON snapshot |

## Graph schema

Written during extraction (structural only):

```
(:Document)-[:CONTAINS]->(:Mention)-[:EXPRESSES]->(:Proposition)
(:Proposition)-[:SUBJECT_ENTITY]->(:Entity)      // only when the subject is a real entity
(:Proposition)-[:OBJECT_ENTITY]->(:Entity)
```

Written only by the resolution pass, each carrying `method`, `confidence`, `evidence` (and `rationale`):

```
REFERS_TO  QUALIFIES  EXCEPTS_FROM  SUPPORTS  CONTRADICTS  DUPLICATE_OF
```

Operational nodes: `(:Checkpoint)` per clause (`done` | `quarantined`), `(:Quarantine)` holding the
raw model response and error for clauses that never produced a valid result.

`Proposition.references_json` keeps every reference (`surface_text`, `kind`, `candidate_ids`,
`resolved_id`, `method`, `confidence`). Unresolved references stay unresolved.

## Guarantees (acceptance criteria)

| Criterion | How it is met |
|-----------|---------------|
| Every proposition has a verifiable source passage | `source_quote` must be found in the clause text (exact, then whitespace/quote-insensitive); the Mention stores real offsets of the original text |
| Page/clause references intact | Mention has `page_start/end`, `section`, `clause_number`, offsets |
| Invalid responses retried or quarantined | Retry with error feedback up to `EXTRACTION_MAX_RETRIES`, then `:Quarantine` + checkpoint `quarantined` |
| Re-runs never duplicate | Deterministic ids + `MERGE`; per-clause checkpoint; `resolve` replaces inferred edges |
| Unresolved references are safe | Only a single plausible antecedent (or a confident adjudicator) resolves; otherwise candidates are recorded |
| Relations only after extraction | `resolve` refuses unless every clause is `done` or `quarantined` |
| Inferred edges carry evidence/method/confidence | Enforced by the `Relation` model |
| JSON export | `export` command / `build_snapshot()` |

## Tests

```bash
pytest
```

Tests use a fake Ollama backend and an in-memory repository, so they need neither Ollama nor Neo4j.
The PDF test builds a small contract with PyMuPDF.

## Known limits / next steps

- Scanned PDFs raise `ScannedPdfError`; add OCR (e.g. `ocrmypdf`) before ingesting.
- Clause detection is heuristic (numbered headings). Unusual layouts (multi-column, tables) may need a tuned `segmenter.py`.
- Entity creation is deliberately conservative (capitalised/defined terms only); no cross-alias merging yet.
- `Argument` nodes for multi-premise reasoning are intentionally left for the reasoning-engine stage.
- Extraction quality depends on the Ollama model; `OLLAMA_MODEL` is configurable so models can be compared.
