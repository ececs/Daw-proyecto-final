"""Core Ticket Engine API Router.

Integrates advanced Ticket resource CRUD mappings incorporating param-hashed Redis caches,
sequential audit tracking, hybrid semantic/lexical search rankings (pgvector), and 
concurrent streaming SSE diagnostic generation routines with built-in telemetry hooks.
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
CACHE_TTL = 60

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
    """Resolves raw string references into robust validated Ticket instances.

    Parses and normalizes sequential long identifiers or standard UUIDv4 hashes.
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
    """Aggregates, filters, and searches persistent Ticket resource collections.

    Derives dynamic MD5 cache identifiers using the combination of applied query parameters,
    preventing redundant vector distance processing or intensive database joins.
    Applies Reciprocal Rank Fusion if semantic indexing parameters are active.
    """
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
        selectinload(Ticket.author),
        selectinload(Ticket.assignee),
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
    """Persists new Ticket entities executing global cache flushes."""
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
    """Extracts fully loaded ticket node details targeting specific cache keys."""
    cache_key = f"{CACHE_PREFIX}detail:{ticket_ref}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return TicketOut.model_validate(cached)

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
    """Processes delta updates on validated ticket instances invalidating cache keys."""
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
    """Retrieves chronological transition states reflecting ticket auditing trails."""
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
    """Generates contextual AI response drafts wrapping calls inside transactional telemetries.

    Raises:
        HTTPException (502): Raised when remote LLM providers respond with connection errors.
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    preferred_provider = body.preferred_provider or "auto"
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
    """Permanently removes Incident logs requiring direct author validations.

    Triggers global WebSockets push alerts notifying connected clients about deletion.
    """
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
    """Issues internal alerts asking verified authors to clear foreign tickets."""
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
    """Initiates Server-Sent Events streams calculating real-time multi-agent RAG diagnostics.

    Retrieves parallel context injections, feeds diagnostic generator loops, and yields
    incremental token packets finalizing monetary execution metrics on connection termination.
    """
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
    """Queries internal DB indices retrieving parsed remote client web scraping text nodes."""
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    result = await db.execute(
        select(KnowledgeChunk)
        .where(
            func.json_extract_path_text(KnowledgeChunk.chunk_metadata, "ticket_id") == str(ticket.id),
            func.json_extract_path_text(KnowledgeChunk.chunk_metadata, "type") == "client_web_context",
        )
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
    """Spawns detached backplane routines refreshing remote vector crawl caches."""
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    if not ticket.client_url:
        raise HTTPException(status_code=400, detail="Ticket has no URL to scrape.")
    asyncio.create_task(scraping_service.scrape_and_index_url(ticket.id, ticket.client_url))
    return {"status": "scraping_started"}


async def _embed_ticket(ticket_id: uuid.UUID, title: str, description: str | None) -> None:
    """Asynchronous secondary execution routine updating multidimensional vector vectors."""
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
