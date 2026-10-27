"""Using legal_graph_ingest from your own Python program."""
from legal_graph_ingest import GraphIngestor, ingest_pdf

# --- 1. One call, no database: get the graph back as Python objects --------------------
doc = ingest_pdf("contract.pdf", in_memory=True, ollama_model="llama3.1:8b")
for p in doc.propositions:
    print(p.modality.value, "|", p.normalized_text)
    print("   source:", p.source_quote)
for r in doc.relations:
    print(r.relation_type.value, r.source_id, "->", r.target_id, f"({r.confidence:.2f}, {r.method})")

# --- 2. Persist to Neo4j and query later -------------------------------------------------
with GraphIngestor(
    ollama_model="llama3.1:8b",
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="change-me",
) as g:
    report = g.ingest("contract.pdf", progress=lambda n, total, head: print(f"{n}/{total} {head}"))
    print(report.summary())

    for p in g.propositions(report.document_id):
        unresolved = [r.surface_text for r in p.references if not r.resolved_id]
        if unresolved:
            print("needs review:", p.normalized_text, unresolved)

    g.export_json(report.document_id, "exports/contract.json")

# --- 3. Later, in another process: read without needing Ollama ----------------------------
# with GraphIngestor(neo4j_password="change-me") as g:
#     props = g.propositions("doc_xxxxxxxxxxxxxxxx")
