"""Knowledge-base ingestion endpoints.

Entry point for adding external web pages to the RAG knowledge store. The
URL is fetched, parsed, split into chunks, embedded and persisted as
`KnowledgeChunk` rows so the AI copilot can retrieve them at query time.
"""

from fastapi import APIRouter, HTTPException, status
from app.core.dependencies import CurrentUser, DB
from app.schemas.knowledge import IngestRequest, IngestResponse
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a URL into the AI knowledge base",
)
async def ingest_url(body: IngestRequest, db: DB, current_user: CurrentUser):
    """Scrape a URL and index its content into the RAG knowledge base.

    Delegates to `knowledge_service.ingest_url`, which validates the URL
    against the domain allow-list, fetches and cleans the HTML, chunks the
    text and persists embeddings for every chunk.

    Args:
        body: Request payload carrying the target URL.
        db: Async SQLAlchemy session.
        current_user: Authenticated requester.

    Returns:
        IngestResponse: Number of chunks indexed and metadata of the source.

    Raises:
        HTTPException: **422** if the URL is rejected (blocked domain,
            parsing failure, etc.).
    """
    try:
        return await knowledge_service.ingest_url(db, str(body.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
