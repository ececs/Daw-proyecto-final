"""Knowledge Ingestion API endpoint layer.

Exposes routes triggering advanced distributed web scraping routines and Matryoshka
vector mapping pipelines supporting dynamic RAG context availability.
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
    """Parses and vectorizes remote web content injecting chunks into the RAG store.

    Fires synchronous extraction routines creating searchable dimensional arrays
    ready for localized cosine distance querying.

    Args:
        body: Schema validating incoming crawling target constraints.
        db: Active asynchronous database transactional handler.
        current_user: Injected token session identifying current operator identity.

    Raises:
        HTTPException (422): Emitted upon domain blacklist matches or parsing failures.

    Returns:
        IngestResponse: Summary object defining chunks written and metadata parsed.
    """
    try:
        return await knowledge_service.ingest_url(db, str(body.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
