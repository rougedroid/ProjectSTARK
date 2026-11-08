from legal_graph_ingest import GraphIngestor

with GraphIngestor(ollama_model="YOUR_INSTALLED_MODEL", neo4j_password="YOUR_PASSWORD") as g:
    props = g.add_rule("If the Client pays all outstanding fees, the Client becomes eligible for closure.")
    for p in props:
        print(p.proposition_id, p.logic.model_dump() if p.logic else "No logical IR returned")
