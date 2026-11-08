from legal_graph_ingest import GraphIngestor

with GraphIngestor(
    ollama_model="gemma3n:e4b",
    neo4j_uri="bolt://localhost:7687", 
    neo4j_username="neo4j", 
    neo4j_password="starkindustries",
    neo4j_database="parser-test-3"
) as graph:

    report = graph.ingest("contract.pdf")

    rules = graph.add_rule(
        "If the Client pays all outstanding fees, the Agreement terminates.",
        document_id=report.document_id
    )

    for rule in rules:
        print(rule.normalized_text)
        print(rule.logic)