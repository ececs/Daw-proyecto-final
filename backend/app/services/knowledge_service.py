"""
RAG knowledge service — scrape, chunk, embed, store, and retrieve.

Flow:
  ingest_url()  — fetch a URL with trafilatura, split into ~500-char chunks,
                  generate embeddings, delete old chunks for the same URL,
                  bulk-insert new ones.
  search()      — embed a query and return the top-k most similar chunks.
                  Falls back to full-text ILIKE if no API key is available.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_chunk import KnowledgeChunk
from app.schemas.knowledge import IngestResponse
from app.services.embedding_service import generate_embedding

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@dataclass
class KnowledgeSearchStats:
    chunks: list[KnowledgeChunk]
    source_type: str

    @property
    def hits(self) -> int:
        return len(self.chunks)


def _chunk_text(text: str) -> list[str]:
    """
    Split text into overlapping chunks of ~CHUNK_SIZE chars.

    Splits on paragraph boundaries first, then merges short paragraphs
    until the target size is reached.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_SIZE:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if current:
                chunks.append(current)
            # Para itself longer than CHUNK_SIZE — hard-split it
            while len(para) > CHUNK_SIZE:
                chunks.append(para[:CHUNK_SIZE])
                para = para[CHUNK_SIZE - CHUNK_OVERLAP:]
            current = para

    if current:
        chunks.append(current)

    return chunks


async def ingest_url(db: AsyncSession, url: str) -> dict:
    """
    Scrape a URL, chunk, embed, and persist to knowledge_chunks.

    Idempotent: deletes any existing chunks for the URL before inserting.

    Returns:
        {"url": str, "chunks_created": int}

    Raises:
        ValueError if the URL could not be scraped or yields no text.
    """
    import trafilatura

    raw_html = await asyncio.to_thread(trafilatura.fetch_url, url)
    if not raw_html:
        raise ValueError(f"Could not fetch URL: {url}")

    text = await asyncio.to_thread(
        trafilatura.extract,
        raw_html,
        include_comments=False,
        include_tables=True,
    )
    if not text:
        raise ValueError(f"Could not extract text from URL: {url}")

    chunks = _chunk_text(text)
    if not chunks:
        raise ValueError("No content found after chunking")

    # Embed all chunks concurrently
    embeddings: list[Optional[list[float]]] = await asyncio.gather(
        *[generate_embedding(c, task_type="RETRIEVAL_DOCUMENT") for c in chunks]
    )

    # Remove stale chunks for this URL (idempotent re-index)
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.url == url))

    rows = [
        KnowledgeChunk(
            url=url,
            chunk_index=i,
            content=chunk,
            embedding=emb,
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    db.add_all(rows)
    await db.commit()

    logger.info("Ingested %d chunks from %s", len(rows), url)
    return IngestResponse(url=url, chunks_created=len(rows))


def _extract_text(content: bytes, mime_type: str) -> str:
    """
    Extract plain text from file bytes based on MIME type.

    Supports the three RAG-eligible types:
      - application/pdf            → pypdf page-by-page extraction
      - text/plain                 → direct UTF-8 decode
      - application/vnd...docx    → python-docx paragraph join

    Raises ValueError for unsupported types so callers can surface a clean error.
    """
    if mime_type == "application/pdf":
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n\n".join(
            page.extract_text() or "" for page in reader.pages
        ).strip()

    if mime_type == "text/plain":
        return content.decode("utf-8", errors="replace").strip()

    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        import io
        import docx
        doc = docx.Document(io.BytesIO(content))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    raise ValueError(f"Unsupported MIME type for text extraction: {mime_type}")


async def ingest_attachment(
    db: AsyncSession,
    attachment_id: str,
    ticket_id: str,
    content: bytes,
    mime_type: str,
) -> dict:
    """
    Extract text from an attachment, chunk, embed, and persist to knowledge_chunks.

    Uses a synthetic url of ``attachment:<attachment_id>`` as the stable key so
    existing chunks can be replaced idempotently on re-toggle.

    Returns:
        {"attachment_id": str, "chunks_created": int}

    Raises:
        ValueError if text extraction fails or yields no content.
    """
    text = _extract_text(content, mime_type)
    if not text:
        raise ValueError("No text content found in attachment")

    chunks = _chunk_text(text)
    if not chunks:
        raise ValueError("No content found after chunking")

    embeddings = await asyncio.gather(
        *[generate_embedding(c, task_type="RETRIEVAL_DOCUMENT") for c in chunks]
    )

    synthetic_url = f"attachment:{attachment_id}"
    # Remove any stale chunks for this attachment (idempotent re-index)
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.url == synthetic_url))

    rows = [
        KnowledgeChunk(
            url=synthetic_url,
            chunk_index=i,
            content=chunk,
            embedding=emb,
            chunk_metadata={"ticket_id": ticket_id, "attachment_id": attachment_id, "type": "attachment"},
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    db.add_all(rows)
    await db.commit()

    logger.info("Ingested %d chunks from attachment %s", len(rows), attachment_id)
    return {"attachment_id": attachment_id, "chunks_created": len(rows)}


async def delete_attachment_chunks(db: AsyncSession, attachment_id: str) -> None:
    """Remove all knowledge chunks associated with an attachment."""
    synthetic_url = f"attachment:{attachment_id}"
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.url == synthetic_url))
    await db.commit()


async def search(db: AsyncSession, query: str, k: int = 5, ticket_id: Optional[str] = None) -> list[str]:
    """
    Return the top-k knowledge chunks most relevant to `query`.
    If ticket_id is provided, prioritizes or limits to chunks linked to that ticket.
    """
    stats = await search_with_stats(db, query=query, k=k, ticket_id=ticket_id)
    return [row.content for row in stats.chunks]


def _apply_ticket_filter(stmt, ticket_id: Optional[str]):
    if ticket_id:
        from sqlalchemy import func
        stmt = stmt.where(func.json_extract_path_text(KnowledgeChunk.chunk_metadata, "ticket_id") == str(ticket_id))
    return stmt


def _detect_source_type(chunks: list[KnowledgeChunk]) -> str:
    types = set()
    for chunk in chunks:
        metadata = chunk.chunk_metadata or {}
        chunk_type = metadata.get("type")
        if chunk_type == "client_web_context":
            types.add("web")
        elif chunk_type == "attachment":
            types.add("attachment")
        else:
            types.add("global")
    if not types:
        return "none"
    if len(types) > 1:
        return "mixed"
    return next(iter(types))


async def search_with_stats(
    db: AsyncSession, query: str, k: int = 5, ticket_id: Optional[str] = None
) -> KnowledgeSearchStats:
    query_embedding = await generate_embedding(query, task_type="RETRIEVAL_QUERY")

    if query_embedding is not None:
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.embedding.isnot(None))  # type: ignore[attr-defined]
        )
        stmt = _apply_ticket_filter(stmt, ticket_id)
        stmt = stmt.order_by(KnowledgeChunk.embedding.cosine_distance(query_embedding))  # type: ignore[attr-defined]
        stmt = stmt.limit(k)
    else:
        pattern = f"%{query}%"
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.content.ilike(pattern))
        stmt = _apply_ticket_filter(stmt, ticket_id)
        stmt = stmt.limit(k)

    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return KnowledgeSearchStats(chunks=chunks, source_type=_detect_source_type(chunks))
