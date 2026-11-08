"""Neo4j constraints and indexes (idempotent)."""

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.document_id IS UNIQUE",
    "CREATE CONSTRAINT mention_id IF NOT EXISTS FOR (n:Mention) REQUIRE n.mention_id IS UNIQUE",
    "CREATE CONSTRAINT proposition_id IF NOT EXISTS FOR (n:Proposition) REQUIRE n.proposition_id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE",
    "CREATE CONSTRAINT checkpoint_key IF NOT EXISTS FOR (n:Checkpoint) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT quarantine_id IF NOT EXISTS FOR (n:Quarantine) REQUIRE n.quarantine_id IS UNIQUE",
    "CREATE INDEX mention_doc IF NOT EXISTS FOR (n:Mention) ON (n.document_id)",
    "CREATE INDEX proposition_doc IF NOT EXISTS FOR (n:Proposition) ON (n.document_id)",
    "CREATE INDEX entity_doc IF NOT EXISTS FOR (n:Entity) ON (n.document_id)",
]
