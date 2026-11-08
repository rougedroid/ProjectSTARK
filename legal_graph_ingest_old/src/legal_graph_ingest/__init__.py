"""legal_graph_ingest: contract PDF -> source-grounded proposition graph in Neo4j.

Typical use:

    from legal_graph_ingest import GraphIngestor, ingest_pdf
"""
from .api import GraphIngestor, IngestedDocument, ingest_pdf
from .config import Settings
from .models.document import DocumentRecord
from .models.mention import Mention
from .models.proposition import Entity, Modality, Polarity, Proposition, Reference
from .models.relation import Relation, RelationType
from .pipeline import IngestPipeline, IngestReport
from .storage.memory import InMemoryRepository
from .storage.repository import Neo4jRepository, Repository

__version__ = "0.1.0"

__all__ = [
    "GraphIngestor", "IngestedDocument", "ingest_pdf", "Settings",
    "IngestPipeline", "IngestReport",
    "DocumentRecord", "Mention", "Proposition", "Entity", "Reference", "Modality", "Polarity",
    "Relation", "RelationType",
    "Repository", "InMemoryRepository", "Neo4jRepository",
]
