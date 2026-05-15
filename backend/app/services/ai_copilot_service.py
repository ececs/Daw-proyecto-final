"""AI Technical Support Co-pilot orchestration service.

Facilitates automatic diagnostic routines, context-enriched reply drafting,
and solution proposals. Blends real-time ticket attributes, historical thread
comments, vectorized local knowledge caches (RAG), and direct LLM execution
with streaming token generator interfaces.
"""

import asyncio
import logging
from typing import Optional
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.models.comment import Comment
from app.ai.agent import get_llm
from app.services.ai_metrics_service import AIRunTracker, estimate_tokens
from app.services.knowledge_service import search_with_stats

logger = logging.getLogger(__name__)


async def _fetch_ticket_and_comments(db: AsyncSession, ticket_id: uuid.UUID):
    """Concurrently retrieves primary ticket profiles and their recent dialogue logs.

    Limits historical window to ensure prompt compacting constraints are satisfied.
    """
    ticket_task = db.execute(
        select(Ticket)
        .options(selectinload(Ticket.author), selectinload(Ticket.assignee))
        .where(Ticket.id == ticket_id)
    )
    comments_task = db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at.desc())
        .limit(5)
    )
    ticket_res, comments_res = await asyncio.gather(ticket_task, comments_task)
    return ticket_res.scalar_one_or_none(), comments_res.scalars().all()


def _format_comments(comments: list[Comment]) -> str:
    """Serializes raw comment entities into a compact formatted prompt context string."""
    comment_list = [
        f"- {c.author.display_name if c.author else 'System'}: {c.content}" 
        for c in reversed(list(comments))
    ]
    return "\n".join(comment_list)


async def _collect_rag_context(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    search_query: str,
    tracker: AIRunTracker | None = None,
    *,
    log_prefix: str,
) -> str:
    """Executes concurrent local and global vector searches returning compiled contexts.

    Tracks hits, misses, and source metadata within optional operational trackers.
    """
    rag_text = "No specific information found in the knowledge base."
    try:
        global_task = search_with_stats(db, query=search_query, k=2)
        ticket_web_task = search_with_stats(db, query=search_query, k=3, ticket_id=str(ticket_id))
        global_ctx, web_ctx = await asyncio.gather(global_task, ticket_web_task)
        
        all_context = []
        if tracker:
            tracker.record_rag(1, web_ctx.hits, web_ctx.source_type)
            tracker.record_rag(1, global_ctx.hits, global_ctx.source_type)
        if web_ctx.chunks:
            all_context.append("CLIENT WEB CONTEXT:\n" + "\n".join(chunk.content for chunk in web_ctx.chunks))
        if global_ctx.chunks:
            all_context.append("GLOBAL / HISTORICAL KNOWLEDGE:\n" + "\n".join(chunk.content for chunk in global_ctx.chunks))
        if all_context:
            rag_text = "\n\n---\n\n".join(all_context)
    except Exception as rag_err:
        logger.error(f"AI Co-pilot: {log_prefix} RAG search failed: {rag_err}")
    return rag_text


async def _prepare_diagnosis_context(
    db: AsyncSession, ticket_id: uuid.UUID, tracker: AIRunTracker | None = None
):
    """Assembles instruction blueprints and user context dictionaries for diagnostics."""
    ticket, comments = await _fetch_ticket_and_comments(db, ticket_id)
    if not ticket:
        return None, None, None

    comments_text = _format_comments(comments)
    search_query = f"{ticket.title} {ticket.description or ''}"
    rag_text = await _collect_rag_context(
        db,
        ticket_id,
        search_query,
        tracker=tracker,
        log_prefix="diagnosis",
    )

    system_prompt = (
        "You are an expert technical support 'AI Co-pilot'. Your mission is to help the technician resolve "
        "this ticket in the most efficient way possible.\n\n"
        "RULES:\n"
        "1. Be concise and professional.\n"
        "2. Identify the probable root cause.\n"
        "3. Propose a step-by-step solution.\n"
        "4. Use the context from the knowledge base if relevant."
    )

    user_prompt = (
        f"TICKET CONTEXT:\n"
        f"Title: {ticket.title}\n"
        f"Description: {ticket.description or 'No description provided.'}\n"
        f"Author: {ticket.author.display_name if ticket.author else 'Unknown'}\n"
        f"Priority: {ticket.priority.value if hasattr(ticket.priority, 'value') else 'medium'}\n\n"
        f"CLIENT CONTEXT:\n"
        f"{ticket.client_summary or 'No additional information available.'}\n\n"
        f"COMMENTS HISTORY:\n{comments_text or 'No comments.'}\n\n"
        f"TECHNICAL KNOWLEDGE (RAG):\n{rag_text}\n\n"
        f"Provide a suggested solution."
    )

    return system_prompt, user_prompt, ticket


async def _prepare_reply_context(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    resolution_note: str,
    tracker: AIRunTracker | None = None,
):
    """Synthesizes professional reply framing prompts incorporating resolution inputs."""
    ticket, comments = await _fetch_ticket_and_comments(db, ticket_id)
    if not ticket:
        return None, None, None

    comments_text = _format_comments(comments)
    search_query = f"{ticket.title} {ticket.description or ''} {resolution_note}"
    rag_text = await _collect_rag_context(
        db,
        ticket_id,
        search_query,
        tracker=tracker,
        log_prefix="reply",
    )

    system_prompt = (
        "You are an AI writing assistant for a professional ticketing system. "
        "Write a final comment draft that a technician can post on the ticket.\n\n"
        "RULES:\n"
        "1. Treat the technician resolution note as the primary source of truth.\n"
        "2. Do not invent steps, fixes, or results that are not supported by the note or context.\n"
        "3. Be clear, concise, professional, and practical.\n"
        "4. Write in the same language implied by the technician note; if unclear, use English.\n"
        "5. Produce comment-ready text only, not explanations about your reasoning.\n"
        "6. If some detail is uncertain, use prudent language instead of making things up."
    )

    user_prompt = (
        f"TECHNICIAN RESOLUTION NOTE (PRIMARY SOURCE):\n"
        f"{resolution_note}\n\n"
        f"TICKET CONTEXT:\n"
        f"Title: {ticket.title}\n"
        f"Description: {ticket.description or 'No description provided.'}\n"
        f"Status: {ticket.status.value if hasattr(ticket.status, 'value') else ticket.status}\n"
        f"Priority: {ticket.priority.value if hasattr(ticket.priority, 'value') else ticket.priority}\n"
        f"Author: {ticket.author.display_name if ticket.author else 'Unknown'}\n"
        f"Assignee: {ticket.assignee.display_name if ticket.assignee else 'Unassigned'}\n\n"
        f"CLIENT CONTEXT:\n"
        f"{ticket.client_summary or 'No additional information available.'}\n\n"
        f"RECENT COMMENTS:\n{comments_text or 'No comments.'}\n\n"
        f"TECHNICAL KNOWLEDGE (RAG):\n{rag_text}\n\n"
        f"Write a short professional comment draft suitable to post on the ticket. "
        f"Focus on what was done, the outcome, and any next step only if supported by the provided information."
    )

    return system_prompt, user_prompt, ticket


async def get_ticket_diagnosis(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    tracker: AIRunTracker | None = None,
    preferred_provider: str | None = None,
) -> str:
    """Generates a complete, non-streaming diagnostic report for a ticket.

    Tracks total execution and prompt costs into the provided telemetry tracker.
    """
    try:
        sys_p, user_p, _ = await _prepare_diagnosis_context(db, ticket_id, tracker=tracker)
        if not sys_p:
            return "Error: Ticket not found."

        llm = get_llm(preferred_provider)
        response = await llm.ainvoke([
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p}
        ])
        if tracker:
            tracker.input_tokens += estimate_tokens(sys_p) + estimate_tokens(user_p)
            tracker.append_output(response.content if isinstance(response.content, str) else str(response.content))
        return response.content
    except Exception as e:
        logger.error(f"AI Co-pilot Error: {str(e)}", exc_info=True)
        return f"*(Co-pilot internal error: {str(e)})*"


async def get_ticket_reply_draft(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    resolution_note: str,
    tracker: AIRunTracker | None = None,
    preferred_provider: str | None = None,
) -> str:
    """Produces a fully structured, formal resolution response ready for user validation."""
    try:
        sys_p, user_p, _ = await _prepare_reply_context(
            db,
            ticket_id,
            resolution_note,
            tracker=tracker,
        )
        if not sys_p:
            return "Error: Ticket not found."

        llm = get_llm(preferred_provider)
        response = await llm.ainvoke([
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ])
        if tracker:
            tracker.input_tokens += estimate_tokens(sys_p) + estimate_tokens(user_p)
            tracker.append_output(response.content if isinstance(response.content, str) else str(response.content))
        content = response.content if isinstance(response.content, str) else str(response.content)
        return content.strip()
    except Exception as e:
        logger.error(f"AI Reply Draft Error: {str(e)}", exc_info=True)
        if tracker:
            tracker.error_message = str(e)
        raise


async def stream_ticket_diagnosis(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    tracker: AIRunTracker | None = None,
    preferred_provider: str | None = None,
):
    """Asynchronous generator yielding sequential diagnosis chunks in real-time.

    Leverages dynamic agent stream events registering token completions iteratively.
    """
    try:
        sys_p, user_p, _ = await _prepare_diagnosis_context(db, ticket_id, tracker=tracker)
        if not sys_p:
            yield {"type": "error", "content": "Ticket no encontrado."}
            return

        llm = get_llm(preferred_provider)
        payload = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p}
        ]
        if tracker:
            tracker.input_tokens += estimate_tokens(sys_p) + estimate_tokens(user_p)

        async for event in llm.astream_events(payload, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_start" and tracker:
                tracker.register_model(event.get("name"))
            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    text = str(chunk.content)
                    if tracker:
                        tracker.append_output(text)
                    yield {"type": "token", "content": text}
    except Exception as e:
        logger.error(f"AI Co-pilot Stream Error: {str(e)}", exc_info=True)
        if tracker:
            tracker.error_message = str(e)
        yield {"type": "error", "content": f"*(Error interno en el flujo del Co-pilot: {str(e)})*"}
