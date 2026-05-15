"""Vector knowledge base schema integrations.

Defines structures for RAG ingestion requests and corresponding parsing metrics.
"""

from pydantic import BaseModel, HttpUrl

class IngestRequest(BaseModel):
    """Validation schema for initiating vectorized content URL crawling."""
    url: HttpUrl

class IngestResponse(BaseModel):
    """Analytical summary documenting execution metrics for an ingestion task."""
    url: str
    chunks_created: int
