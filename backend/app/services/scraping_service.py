"""Asynchronous background URL scrapers and indexers.

Offloads CPU-bound web extraction processes to dedicated threaded execution,
leveraging trafilatura for optimal noise removal. Persists vector context and distributes
real-time telemetry notifying users upon scrape finalization.
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
    """Fetches a URL, sanitizes rich HTML layouts, and indexes embeddings as background task.

    Uses asyncio execution wrappers preventing blocking locks on the primary main-loop.
    Broadcasts localized UI status notifications at analysis start and completion.

    Args:
        ticket_id: Target ticket reference UUID for contextual binding.
        url: Remote client HTTP address to crawl and process.
    """
    logger.info(f"Scraping Service: Starting analysis for ticket {ticket_id} -> {url}")
    
    # Notify that analysis has started
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
        # 1. Download and extract text (Offloaded to a thread to avoid blocking)
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
        if not downloaded:
            logger.error(f"Scraping Service: Failed to fetch URL {url}")
            return
            
        text = await asyncio.to_thread(trafilatura.extract, downloaded)
        if not text:
            logger.error(f"Scraping Service: No meaningful text found in {url}")
            return
            
        # 2. Content Preparation
        content = text[:4000] 
        
        # 3. Generate embedding
        from app.services.embedding_service import generate_embedding
        embedding = await generate_embedding(content, task_type="RETRIEVAL_DOCUMENT")
        
        if embedding is None:
            logger.warning(f"Scraping Service: Could not generate embedding for {url}")
            return

        # 4. Persistence
        async with async_session_factory() as db:
            # 4.1 Save to Knowledge base (RAG)
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

            # 4.2 Seed client_summary on first scrape only
            from app.models.ticket import Ticket
            from sqlalchemy import select
            ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = ticket_res.scalar_one_or_none()

            if ticket and not (ticket.client_summary or "").strip():
                snippet = content[:1500].strip()
                ticket.client_summary = snippet

            await db.commit()
            
        # 5. Notify via WebSocket (Live UI update) + persist notification
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
