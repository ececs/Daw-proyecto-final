"""Google Gemini vector embedding integration provider.

Manages asynchronous HTTP calls to the Google Generative AI API executing high-dimensional
vector transformations. Configured to yield optimized 768-dimensional arrays using the
Matryoshka Representation Learning standard (gemini-embedding-2) to optimize PostgreSQL
index performance and memory layouts.
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIM = 768
_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"


async def generate_embedding(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> Optional[list[float]]:
    """Generates a 768-dimensional semantic vector array for arbitrary text.

    Conforms to context size parameters, truncating source inputs to avoid API faults.

    Args:
        text: Source raw textual content to undergo transformation.
        task_type: Retrieval intent identifier. Valid: 'RETRIEVAL_DOCUMENT' or 'RETRIEVAL_QUERY'.

    Returns:
        Optional[list[float]]: Optimized floating-point array if successful, otherwise None.
    """
    from app.core.config import settings

    if not settings.GOOGLE_API_KEY:
        return None

    url = _EMBED_URL.format(model=EMBEDDING_MODEL)
    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {"parts": [{"text": text[:2000]}]},
        "taskType": task_type,
        "outputDimensionality": EMBEDDING_DIM,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json=payload,
                params={"key": settings.GOOGLE_API_KEY},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]

    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None


async def generate_ticket_embedding(title: str, description: Optional[str] = None) -> Optional[list[float]]:
    """Constructs an specialized semantic vector representing a Ticket record.

    Combines summary titles and structural descriptions into a unified input context.

    Args:
        title: The foundational subject/title line of the ticket.
        description: Detailed incident notes describing the issue.

    Returns:
        Optional[list[float]]: Combined semantic embedding vector array.
    """
    text = title
    if description:
        text = f"{title}\n\n{description}"
    return await generate_embedding(text, task_type="RETRIEVAL_DOCUMENT")
