"""AI co-pilot service for the support workflow.

Orchestrates two LLM-backed features exposed by the ticket API:

- **Diagnosis** — given a ticket, produce a step-by-step suggested fix.
- **Reply draft** — given a technician's resolution note, write a polished
  comment ready to be posted on the ticket.

Both features share the same context-building pipeline (ticket details,
recent comments, RAG over the knowledge base) and the same telemetry
plumbing (`AIRunTracker`) used to compute cost and token metrics.
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
    """Load the ticket and its 5 most recent comments concurrently.

    The comment window is capped so the prompt stays within the model's
    context budget regardless of how chatty the ticket is.
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
    """Render a comment list as a compact `- author: text` block for the prompt."""
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
    """Run the global and per-ticket RAG searches in parallel and merge results.

    Two retrievals are issued concurrently: one over the global knowledge
    base (`k=2`) and one restricted to chunks tagged with this ticket id
    (typically scraped client web context, `k=3`). Hits, source type and
    counts are forwarded to the tracker so the AIRun metrics are accurate.
    Failures degrade gracefully: the function returns a "no information"
    sentinel instead of raising.
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
    """Build the system and user prompts used by the diagnosis feature.

    Returns:
        tuple: `(system_prompt, user_prompt, ticket)` or `(None, None, None)`
        if the ticket does not exist.
    """
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
    """Build the system and user prompts used by the reply-draft feature.

    The technician's `resolution_note` is treated as the primary source of
    truth; ticket metadata, comments and RAG hits are secondary context
    used to phrase the draft in a way that fits the conversation.
    """
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
    """Run a non-streaming diagnosis and return the full text.

    Args:
        db: Async SQLAlchemy session.
        ticket_id: Target ticket id.
        tracker: Optional metrics tracker — updated with input/output
            tokens when supplied.
        preferred_provider: Optional override (`openai` / `google` / `auto`).

    Returns:
        str: The diagnosis text, or a `"*(Co-pilot internal error: ...)*"`
        marker if the LLM call fails (the error is also logged).
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
    """Generate a reply draft anchored on the technician's resolution note.

    Unlike `get_ticket_diagnosis`, this function **re-raises** on LLM
    failure so the API layer can convert the error into a 502; the error
    is also recorded on the tracker before being propagated.

    Returns:
        str: A stripped, ready-to-post comment body.
    """
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
    """Yield diagnosis tokens as they are produced by the LLM.

    Consumes LangChain's `astream_events` v2 protocol and emits a dict for
    each chunk so the SSE endpoint can forward them verbatim. Errors are
    emitted as `{"type": "error", ...}` events instead of raising, so the
    HTTP stream can terminate cleanly.

    Yields:
        dict: `{"type": "token", "content": str}` for each token,
        `{"type": "error", "content": str}` if the model fails.
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
