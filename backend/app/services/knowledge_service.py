"""RAG knowledge base pipeline and semantic ingestion service.

Implements standard content chunking, multi-format attachment extraction, and vector-space
distance lookups using pgvector operators. Manages text extraction from binary file uploads
including PDFs, Microsoft Word documents, and plain text assets.
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
    """Data container tracking quantitative outcomes returned by vector searches."""
    chunks: list[KnowledgeChunk]
    source_type: str

    @property
    def hits(self) -> int:
        """Measures the discrete number of valid semantic chunks returned."""
        return len(self.chunks)


def _chunk_text(text: str) -> list[str]:
    """Splits source text arrays into normalized spans utilizing a static overlap boundary.

    Optimized to divide first along paragraph line-breaks before executing hard truncation.
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
            while len(para) > CHUNK_SIZE:
                chunks.append(para[:CHUNK_SIZE])
                para = para[CHUNK_SIZE - CHUNK_OVERLAP:]
            current = para

    if current:
        chunks.append(current)

    return chunks


async def ingest_url(db: AsyncSession, url: str) -> dict:
    """Fetches HTML pages, applies paragraph chunking, embeds, and saves to PostgreSQL.

    Operates idempotently, purging stale historical chunks sharing identical target URLs.

    Raises:
        ValueError: If URL fetch yields zero content or network-level faults occur.
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

    embeddings: list[Optional[list[float]]] = await asyncio.gather(
        *[generate_embedding(c, task_type="RETRIEVAL_DOCUMENT") for c in chunks]
    )

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
    """Dispatches specific binary bytes parsers mapping incoming MIME standards.

    Currently parses PDF (pypdf), DOCX (python-docx), and TXT (UTF-8 codec).
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
    """Parses uploaded file byte contents into vectorized knowledge indexes.

    Synthesizes stable artificial URLs identifying attachment-owned chunk groups.
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
    """Deletes all indexed vector fragments mapped to a single attachment file."""
    synthetic_url = f"attachment:{attachment_id}"
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.url == synthetic_url))
    await db.commit()


async def search(db: AsyncSession, query: str, k: int = 5, ticket_id: Optional[str] = None) -> list[str]:
    """Recover Top-K textual excerpts bearing the highest similarity proximity to queries.

    Delegates search processes to specialized tracking functions.
    """
    stats = await search_with_stats(db, query=query, k=k, ticket_id=ticket_id)
    return [row.content for row in stats.chunks]


def _apply_ticket_filter(stmt, ticket_id: Optional[str]):
    """Appends localized context filtering leveraging PostgreSQL's native JSONB paths."""
    if ticket_id:
        from sqlalchemy import func
        stmt = stmt.where(func.json_extract_path_text(KnowledgeChunk.chunk_metadata, "ticket_id") == str(ticket_id))
    return stmt


def _detect_source_type(chunks: list[KnowledgeChunk]) -> str:
    """Identifies categorical metadata footprints to track active vector sources."""
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
    """Executes vectorized pgvector similarity search or falls back to ILIKE matching.

    Determines the optimal path based on live embedding API operational availability.

    Returns:
        KnowledgeSearchStats: Enriched statistics container summarizing search metadata.
    """
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
