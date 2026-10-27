from legal_graph_ingest import GraphIngestor 

with GraphIngestor(
    ollama_model="gemma3n:e4b",
    neo4j_uri="bolt://localhost:7687", 
    neo4j_username="neo4j", 
    neo4j_password="starkindustries",
    neo4j_database="parser-test"
) as gi:
    report = gi.ingest("ex10-1.htm.pdf")
    print(report.summary())
    print("document id: ", report.document_id)





