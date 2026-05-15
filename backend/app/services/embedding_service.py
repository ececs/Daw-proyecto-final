"""Google Gemini embedding client.

Thin async wrapper over Google's `embedContent` REST endpoint. Returns
768-dimensional vectors (Matryoshka representation) sized to match the
`pgvector` column declared in the migrations. Returns `None` on any
failure — callers are expected to degrade gracefully (e.g. fall back to
keyword search) rather than propagate the error.
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
    """Compute the embedding of `text` using the configured Gemini model.

    The input is truncated to 2 000 characters to stay well under the API
    limits and keep cost bounded. `task_type` should be
    `"RETRIEVAL_DOCUMENT"` when indexing content and
    `"RETRIEVAL_QUERY"` when embedding a user query — Gemini optimises
    the vector differently in each case.

    Returns:
        list[float] | None: The 768-dim vector, or `None` when the API
        key is missing or the request fails (the error is logged at WARN).
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
    """Embed a ticket by concatenating its title and description.

    Returns:
        list[float] | None: The combined embedding, or `None` on failure.
    """
    text = title
    if description:
        text = f"{title}\n\n{description}"
    return await generate_embedding(text, task_type="RETRIEVAL_DOCUMENT")
