"""Knowledge base / RAG pipeline service.

Three responsibilities:

- **Ingest** content (URLs, PDFs, DOCX, plain text) into `KnowledgeChunk`
  rows together with their pgvector embeddings.
- **Search** chunks by cosine similarity, with an `ILIKE` fallback when
  the embedding provider is unavailable.
- **Maintain** the index (idempotent reingest, chunk deletion when an
  attachment is removed or its RAG flag is turned off).
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
    """Result wrapper carrying the matched chunks and a source-type tag.

    `source_type` is used by `AIRunTracker.record_rag` to classify where
    the context came from (`"web"`, `"attachment"`, `"global"`, ...).
    """
    chunks: list[KnowledgeChunk]
    source_type: str

    @property
    def hits(self) -> int:
        """Number of chunks returned by the search."""
        return len(self.chunks)


def _chunk_text(text: str) -> list[str]:
    """Split text into paragraph-aware chunks of at most `CHUNK_SIZE` chars.

    Prefers paragraph (`\\n\\n`) boundaries; when a single paragraph is
    larger than the budget, it is hard-cut with `CHUNK_OVERLAP` characters
    of overlap between consecutive pieces to avoid losing context at the
    seam.
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
    """Fetch a URL, extract its main text and index it as RAG chunks.

    Uses `trafilatura` for boilerplate-free text extraction. The operation
    is idempotent: any previous chunks for the same URL are deleted before
    the new ones are inserted, so re-ingesting always reflects the latest
    snapshot.

    Raises:
        ValueError: If the URL cannot be fetched, no extractable text is
            found, or the chunker produces zero chunks.
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
    """Extract plain text from a binary attachment based on its MIME type.

    Supported types: `application/pdf` (via `pypdf`), `text/plain`
    (UTF-8 decode), and `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
    (DOCX, via `python-docx`).

    Raises:
        ValueError: For unsupported MIME types.
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
    """Extract, chunk and index the text content of a ticket attachment.

    Chunks are tagged with `chunk_metadata` (`ticket_id`, `attachment_id`,
    `type="attachment"`) so the search side can scope retrieval. The
    synthetic URL `attachment:<id>` acts as a stable identifier for
    re-ingestion / deletion.
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
    """Delete every chunk indexed for the given attachment id."""
    synthetic_url = f"attachment:{attachment_id}"
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.url == synthetic_url))
    await db.commit()


async def search(db: AsyncSession, query: str, k: int = 5, ticket_id: Optional[str] = None) -> list[str]:
    """Return the top-K chunk texts matching `query`.

    Thin wrapper around `search_with_stats` for callers that only need the
    raw content strings.
    """
    stats = await search_with_stats(db, query=query, k=k, ticket_id=ticket_id)
    return [row.content for row in stats.chunks]


def _apply_ticket_filter(stmt, ticket_id: Optional[str]):
    """Narrow a chunk-search statement to the chunks tagged with `ticket_id`."""
    if ticket_id:
        from sqlalchemy import func
        stmt = stmt.where(func.json_extract_path_text(KnowledgeChunk.chunk_metadata, "ticket_id") == str(ticket_id))
    return stmt


def _detect_source_type(chunks: list[KnowledgeChunk]) -> str:
    """Classify a list of chunks by their origin metadata.

    Returns one of `"none"`, `"web"`, `"attachment"`, `"global"` or
    `"mixed"` so the metrics layer can attribute RAG hits to a source.
    """
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
    """Run a semantic (pgvector) search with an `ILIKE` fallback.

    If the embedding provider returns `None` (e.g. it is rate-limited or
    not configured), the function still produces useful results via a
    keyword `ILIKE` query, at the cost of recall.

    Returns:
        KnowledgeSearchStats: Matched chunks plus the inferred source type.
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
