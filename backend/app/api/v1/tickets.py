"""
Ticket routes — CRUD + filtering + pagination + sorting + hybrid search.

Search strategy:
  When a `search` query param is provided:
  1. Generate a vector embedding of the query (Google text-embedding-004).
  2. If embedding succeeds → run hybrid search:
     - semantic ranking by cosine similarity against stored ticket embeddings
     - keyword ranking over title/description matches
     - fuse both rankings with Reciprocal Rank Fusion (RRF)
  3. If embedding fails (no API key, service down) → keyword fallback: ilike
     on title and description (same behavior as before pgvector).

  This means the API degrades gracefully in tests and local dev without an
  API key, while delivering hybrid semantic + keyword retrieval in production.

Embedding side-effects on writes:
  - POST /tickets: embedding generated after commit (fire-and-forget).
  - PATCH /tickets/{id}: embedding regenerated if title or description changed.
  Both use asyncio.create_task so they don't add latency to the response.
"""

import asyncio
import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, DB
from app.ai import observability
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User
from app.schemas.ticket import (
    ReplyDraftRequest,
    ReplyDraftResponse,
    TicketCreate,
    TicketListResponse,
    TicketOut,
    TicketUpdate,
)
from app.services.cache_service import cache_get, cache_set, cache_invalidate_prefix
from app.services.embedding_service import generate_ticket_embedding
from app.services import ticket_service, notification_service, ai_copilot_service, scraping_service, ai_metrics_service
from app.schemas.websocket import WSMessageType
from app.models.knowledge_chunk import KnowledgeChunk

CACHE_PREFIX = "tickets:"
CACHE_TTL = 60  # seconds

router = APIRouter(prefix="/tickets", tags=["Tickets"])

SORTABLE_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": Ticket.priority,
    "status": Ticket.status,
    "title": Ticket.title,
    "ticket_number": Ticket.ticket_number,
}


async def _resolve_ticket_or_raise(db: DB, ticket_ref: str) -> Ticket:
    """
    Resolve a ticket reference with stable validation semantics.

    The API accepts both sequential numbers and legacy UUIDs, but malformed
    values should be rejected as validation errors instead of "not found".
    """
    if not ticket_service.is_valid_ticket_ref(ticket_ref):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid ticket reference format",
        )

    ticket = await ticket_service.resolve_ticket(db, ticket_ref)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("", response_model=TicketListResponse, summary="List tickets with filters")
async def list_tickets(
    db: DB,
    current_user: CurrentUser,
    status: TicketStatus | None = Query(None),
    priority: TicketPriority | None = Query(None),
    assignee_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None, description="Hybrid semantic + keyword search (falls back to keyword)"),
    sort_by: str = Query("created_at"),
    order: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
):
    # Cache key = hash of all query params so each search/filter/page combination
    # is cached independently.
    cache_params = {
        "status": status.value if status else None,
        "priority": priority.value if priority else None,
        "assignee_id": str(assignee_id) if assignee_id else None,
        "search": search,
        "sort_by": sort_by,
        "order": order,
        "page": page,
        "size": size,
    }
    cache_key = CACHE_PREFIX + hashlib.md5(
        json.dumps(cache_params, sort_keys=True).encode()
    ).hexdigest()

    cached = await cache_get(cache_key)
    if cached is not None:
        return TicketListResponse(**cached)

    query = select(Ticket).options(
        selectinload(Ticket.author),    # type: ignore[attr-defined]
        selectinload(Ticket.assignee),  # type: ignore[attr-defined]
    )

    if status is not None:
        query = query.where(Ticket.status == status)
    if priority is not None:
        query = query.where(Ticket.priority == priority)
    if assignee_id is not None:
        query = query.where(Ticket.assignee_id == assignee_id)

    if search:
        ranked = await ticket_service.hybrid_search_tickets(db, query, search)
        total = len(ranked)
        tickets = ranked[(page - 1) * size: page * size]
        response = TicketListResponse(items=list(tickets), total=total, page=page, size=size)
        await cache_set(cache_key, response.model_dump(mode="json"), ttl=CACHE_TTL)
        return response

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    sort_column = SORTABLE_COLUMNS.get(sort_by, Ticket.created_at)
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    tickets = result.scalars().all()

    response = TicketListResponse(items=list(tickets), total=total, page=page, size=size)
    await cache_set(cache_key, response.model_dump(mode="json"), ttl=CACHE_TTL)
    return response


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED, summary="Create a ticket")
async def create_ticket(body: TicketCreate, db: DB, current_user: CurrentUser):
    ticket = await ticket_service.create_ticket(
        db=db,
        title=body.title,
        description=body.description,
        priority=body.priority,
        author_id=current_user.id,
        assignee_id=body.assignee_id,
        client_url=body.client_url,
        client_summary=body.client_summary,
    )
    await cache_invalidate_prefix(CACHE_PREFIX)

    return ticket


@router.get("/{ticket_ref}", response_model=TicketOut, summary="Get a ticket by number")
async def get_ticket(ticket_ref: str, db: DB, current_user: CurrentUser):
    cache_key = f"{CACHE_PREFIX}detail:{ticket_ref}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return TicketOut(**cached)

    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    out = TicketOut.model_validate(ticket)
    await cache_set(cache_key, out.model_dump(mode="json"), ttl=CACHE_TTL)
    return out


@router.patch("/{ticket_ref}", response_model=TicketOut, summary="Update a ticket")
async def update_ticket(
    ticket_ref: str,
    body: TicketUpdate,
    db: DB,
    current_user: CurrentUser,
):
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    update_data = body.model_dump(exclude_unset=True)
    updated_ticket = await ticket_service.update_ticket(
        db=db,
        ticket_id=ticket.id,
        update_data=update_data,
        actor=current_user,
    )

    await cache_invalidate_prefix(CACHE_PREFIX)
    return updated_ticket


@router.get("/{ticket_ref}/history", summary="Get audit history for a ticket")
async def get_ticket_history(ticket_ref: str, db: DB, current_user: CurrentUser):
    from app.services import history_service
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    return await history_service.get_history(db, ticket.id)


@router.post("/{ticket_ref}/reply-draft", response_model=ReplyDraftResponse, summary="Generate an AI comment draft")
async def generate_reply_draft(
    ticket_ref: str,
    body: ReplyDraftRequest,
    db: DB,
    current_user: CurrentUser,
):
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    preferred_provider = body.preferred_provider or "auto"
    # Keep the provider-selection rules identical to chat/diagnosis so metrics stay comparable.
    tracker = ai_metrics_service.AIRunTracker(
        surface="reply_draft",
        user_id=current_user.id,
        ticket_id=ticket.id,
        primary_provider=ai_metrics_service.configured_primary_signature()[0] if preferred_provider == "auto" else preferred_provider,
        primary_model="gpt-4o-mini" if preferred_provider == "openai" else ("gemini-2.5-flash" if preferred_provider == "google" else ai_metrics_service.configured_primary_signature()[1]),
        input_tokens=0,
    )
    ai_run = await ai_metrics_service.create_ai_run(
        db,
        user_id=current_user.id,
        surface="reply_draft",
        ticket_id=ticket.id,
        thread_id=None,
        estimated_input_tokens=0,
    )
    tracker.ai_run_id = ai_run.id

    try:
        draft = await ai_copilot_service.get_ticket_reply_draft(
            db,
            ticket.id,
            body.resolution_note,
            tracker=tracker,
            preferred_provider=preferred_provider,
        )
        await ai_metrics_service.finalize_ai_run(
            db,
            ai_run,
            tracker,
            success=True,
        )
        return ReplyDraftResponse(draft=draft, ai_run_id=ai_run.id)
    except Exception as exc:
        # Convert provider/library failures into a stable API contract for the frontend.
        await ai_metrics_service.finalize_ai_run(
            db,
            ai_run,
            tracker,
            success=False,
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate AI reply draft.",
        ) from exc


@router.delete("/{ticket_ref}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a ticket")
async def delete_ticket(ticket_ref: str, db: DB, current_user: CurrentUser):
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    if ticket.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el autor puede eliminar este ticket."
        )

    ticket_id = ticket.id
    title = ticket.title

    await db.delete(ticket)
    await db.commit()

    # Notify after commit so the ticket_id FK is already gone
    await notification_service.notify_ticket_deleted(db, ticket_id, title, current_user)
    await db.commit()

    await notification_service.broadcast_global_event(
        type=WSMessageType.TICKET_DELETED,
        data={"id": str(ticket_id), "title": title},
        db=db
    )

    await cache_invalidate_prefix(CACHE_PREFIX)


@router.post("/{ticket_ref}/deletion-request", summary="Ask the author to delete a ticket")
async def request_ticket_deletion(ticket_ref: str, db: DB, current_user: CurrentUser):
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    if ticket.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are the author of this ticket. You can delete it directly.",
        )

    await notification_service.notify_ticket_deletion_requested(
        db,
        ticket=ticket,
        requester=current_user,
    )
    await db.commit()
    return {"ok": True}


from fastapi.responses import StreamingResponse

@router.get("/{ticket_ref}/diagnosis")
async def get_diagnosis(
    ticket_ref: str,
    db: DB,
    current_user: CurrentUser,
    preferred_provider: str | None = None,
):
    """Generate an AI diagnosis and suggested solution for a ticket (streamed)."""
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    observability.increment_diagnosis()
    tracker = ai_metrics_service.AIRunTracker(
        surface="diagnosis",
        user_id=current_user.id,
        ticket_id=ticket.id,
        primary_provider=ai_metrics_service.configured_primary_signature()[0] if (preferred_provider or "auto") == "auto" else preferred_provider,
        primary_model="gpt-4o-mini" if preferred_provider == "openai" else ("gemini-2.5-flash" if preferred_provider == "google" else ai_metrics_service.configured_primary_signature()[1]),
        input_tokens=0,
    )
    ai_run = await ai_metrics_service.create_ai_run(
        db,
        user_id=current_user.id,
        surface="diagnosis",
        ticket_id=ticket.id,
        thread_id=None,
        estimated_input_tokens=0,
    )
    tracker.ai_run_id = ai_run.id

    async def diagnosis_stream():
        success = False
        error_message: str | None = None
        yield f"data: {json.dumps({'type': 'session', 'ai_run_id': str(ai_run.id)})}\n\n"
        try:
            async for event in ai_copilot_service.stream_ticket_diagnosis(
                db,
                ticket.id,
                tracker=tracker,
                preferred_provider=preferred_provider,
            ):
                if event.get("type") == "error":
                    error_message = event.get("content")
                yield f"data: {json.dumps(event)}\n\n"
            if error_message is None:
                success = True
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            await ai_metrics_service.finalize_ai_run(
                db,
                ai_run,
                tracker,
                success=success,
                error_message=error_message,
            )
    return StreamingResponse(
        diagnosis_stream(),
        media_type="text/event-stream"
    )


@router.get("/{ticket_ref}/web-context")
async def get_ticket_web_context(
    ticket_ref: str,
    db: DB,
    current_user: CurrentUser,
):
    """Fetches the latest AI-extracted web context for this ticket."""
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    result = await db.execute(
        select(KnowledgeChunk)
        .where(func.json_extract_path_text(KnowledgeChunk.chunk_metadata, "ticket_id") == str(ticket.id))
        .order_by(KnowledgeChunk.created_at.desc())
        .limit(1)
    )
    chunk = result.scalar_one_or_none()
    return {"content": chunk.content if chunk else None}


@router.post("/{ticket_ref}/web-scrape-refresh")
async def refresh_ticket_web_scrape(
    ticket_ref: str,
    db: DB,
    current_user: CurrentUser,
):
    """Manually triggers a new web scrape for the ticket's URL."""
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    if not ticket.client_url:
        raise HTTPException(status_code=400, detail="Ticket has no URL to scrape.")
    asyncio.create_task(scraping_service.scrape_and_index_url(ticket.id, ticket.client_url))
    return {"status": "scraping_started"}


# ─── Private helpers ──────────────────────────────────────────────────────────


async def _embed_ticket(ticket_id: uuid.UUID, title: str, description: str | None) -> None:
    """
    Background task: generate and persist a ticket's embedding.

    Opens its own DB session (independent of the request session which is
    already closed by the time this task runs).
    """
    embedding = await generate_ticket_embedding(title, description)
    if embedding is None:
        return

    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = result.scalar_one_or_none()
            if ticket:
                ticket.embedding = embedding
                await session.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to persist embedding for %s: %s", ticket_id, exc)
