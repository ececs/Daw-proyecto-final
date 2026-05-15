"""Background URL scraping and indexing for ticket client URLs.

When a ticket has a `client_url`, this service downloads the page, runs
boilerplate-free text extraction (`trafilatura`), embeds the content and
stores it as a `KnowledgeChunk` tagged with `type="client_web_context"`
so the RAG pipeline can use it later. Designed to run as a fire-and-
forget `asyncio.create_task` from the ticket service.
"""

import asyncio
import logging
import trafilatura
import uuid
from typing import Optional

from app.db.session import async_session_factory
from app.models.knowledge_chunk import KnowledgeChunk

logger = logging.getLogger(__name__)


async def scrape_and_index_url(ticket_id: uuid.UUID, url: str) -> None:
    """Scrape a URL associated to a ticket and index it as RAG context.

    Steps:

    1. Notify the author/assignee that analysis started (live UI hint).
    2. Fetch and extract the page text in a thread to avoid blocking the
       event loop (`trafilatura` is synchronous and CPU-bound).
    3. Generate the embedding and persist a `KnowledgeChunk`. On the
       first successful scrape, seed `Ticket.client_summary` with a short
       snippet so the UI has something to show before the AI is invoked.
    4. Broadcast a `WEB_SCRAPE_COMPLETED` live event and persist a
       `rag_indexed` notification for the subscribers.

    Errors are caught and logged: scraping is a best-effort enrichment,
    never a hard failure for the ticket flow.

    Args:
        ticket_id: Ticket the scraped content belongs to.
        url: Remote URL to crawl.
    """
    logger.info(f"Scraping Service: Starting analysis for ticket {ticket_id} -> {url}")

    try:
        async with async_session_factory() as db:
            from app.models.ticket import Ticket
            from sqlalchemy import select
            ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = ticket_res.scalar_one_or_none()

            if ticket:
                from app.services.notification_service import broadcast_live_update
                from app.schemas.websocket import WSMessageType
                users_to_notify = {ticket.author_id}
                if ticket.assignee_id:
                    users_to_notify.add(ticket.assignee_id)

                for uid in users_to_notify:
                    await broadcast_live_update(
                        user_id=uid,
                        ticket_id=ticket_id,
                        type=WSMessageType.SYSTEM_ALERT,
                        message=f"Analyzing URL: {url}..."
                    )
    except Exception as e:
        logger.warning(f"Failed to send start notification: {e}")

    try:
        # Why: `trafilatura` calls are synchronous; offloading them to a
        # thread keeps the event loop free for concurrent requests.
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
        if not downloaded:
            logger.error(f"Scraping Service: Failed to fetch URL {url}")
            return

        text = await asyncio.to_thread(trafilatura.extract, downloaded)
        if not text:
            logger.error(f"Scraping Service: No meaningful text found in {url}")
            return

        # Why: cap the indexed content to keep both the embedding cost
        # and the persisted row size bounded.
        content = text[:4000]

        from app.services.embedding_service import generate_embedding
        embedding = await generate_embedding(content, task_type="RETRIEVAL_DOCUMENT")

        if embedding is None:
            logger.warning(f"Scraping Service: Could not generate embedding for {url}")
            return

        async with async_session_factory() as db:
            chunk = KnowledgeChunk(
                url=url,
                chunk_index=0,
                content=content,
                embedding=embedding,
                chunk_metadata={
                    "source": url,
                    "ticket_id": str(ticket_id),
                    "type": "client_web_context"
                }
            )
            db.add(chunk)

            # Why: only seed `client_summary` the *first* time so manual
            # edits made later by a human are never overwritten.
            from app.models.ticket import Ticket
            from sqlalchemy import select
            ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = ticket_res.scalar_one_or_none()

            if ticket and not (ticket.client_summary or "").strip():
                snippet = content[:1500].strip()
                ticket.client_summary = snippet

            await db.commit()

        if ticket:
            from app.services.notification_service import (
                broadcast_live_update,
                notify_rag_indexed,
            )
            from app.schemas.websocket import WSMessageType

            users_to_notify = {ticket.author_id}
            if ticket.assignee_id:
                users_to_notify.add(ticket.assignee_id)

            for uid in users_to_notify:
                await broadcast_live_update(
                    user_id=uid,
                    ticket_id=ticket_id,
                    type=WSMessageType.WEB_SCRAPE_COMPLETED,
                    message=f"Analysis finished for: {url}"
                )

            async with async_session_factory() as notif_db:
                await notify_rag_indexed(
                    notif_db,
                    ticket_id=ticket_id,
                    author_id=ticket.author_id,
                    assignee_id=ticket.assignee_id,
                    message=f'Website indexed for RAG: {url}',
                )

        logger.info(f"Scraping Service: Successfully indexed web context for ticket {ticket_id}")

    except Exception as e:
        logger.error(f"Scraping Service: Critical error for ticket {ticket_id}: {str(e)}", exc_info=True)
