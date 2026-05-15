"""Ticket REST API.

Exposes the CRUD surface for the `Ticket` aggregate together with the
AI-assisted endpoints used by the support copilot: hybrid keyword + vector
search, audit-history retrieval, reply-draft generation, streaming SSE
diagnosis and on-demand re-scraping of the client URL associated to a
ticket. Responses for read endpoints are memoised in Redis keyed by the
hash of the active query parameters.
"""

import asyncio
import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.ai import observability
from app.core.dependencies import CurrentUser, DB
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.schemas.ticket import (
    ReplyDraftRequest,
    ReplyDraftResponse,
    TicketCreate,
    TicketListResponse,
    TicketOut,
    TicketUpdate,
)
from app.schemas.websocket import WSMessageType
from app.services import (
    ai_copilot_service,
    ai_metrics_service,
    history_service,
    notification_service,
    scraping_service,
    ticket_service,
)
from app.services.cache_service import cache_get, cache_set, cache_invalidate_prefix

CACHE_PREFIX = "tickets:"
CACHE_TTL = 60

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# Allow-list of columns accepted by the `sort_by` query parameter. Acts as a
# defence against SQL injection through user-supplied sort keys.
SORTABLE_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": Ticket.priority,
    "status": Ticket.status,
    "title": Ticket.title,
    "ticket_number": Ticket.ticket_number,
}


async def _resolve_ticket_or_raise(db: DB, ticket_ref: str) -> Ticket:
    """Resolve a ticket reference (UUID or human-readable number) to a Ticket.

    Accepts both the canonical UUID primary key and the short sequential
    `ticket_number` shown in the UI, validates the format and returns the
    fully-loaded ORM instance.

    Args:
        db: Async SQLAlchemy session.
        ticket_ref: Raw reference coming from the URL path.

    Returns:
        Ticket: The resolved ORM instance.

    Raises:
        HTTPException: **422** if the reference is malformed.
        HTTPException: **404** if no ticket matches the reference.
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
    """List tickets with filtering, pagination and optional hybrid search.

    Supports filtering by status, priority and assignee, paginated output
    and sorting on the columns declared in `SORTABLE_COLUMNS`. When the
    `search` parameter is supplied, results are produced by
    `ticket_service.hybrid_search_tickets`, which combines keyword matching
    with pgvector cosine similarity over the ticket embedding.

    The full response is cached in Redis under an MD5 key derived from the
    active query parameters to avoid recomputing vector searches and large
    joins on identical requests.

    Returns:
        TicketListResponse: Page of tickets plus pagination metadata.
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

    # Why: hybrid search has its own ranking and pagination is applied
    # post-ranking; the SQL ORDER BY / LIMIT path is skipped on purpose.
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
    """Create a new ticket authored by the current user.

    Delegates persistence — including embedding generation and optional
    background URL scraping — to `ticket_service.create_ticket`, then
    invalidates the list cache so the new ticket is visible immediately.

    Returns:
        TicketOut: The freshly created ticket.
    """
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


@router.get("/{ticket_ref}", response_model=TicketOut, summary="Get a ticket by reference")
async def get_ticket(ticket_ref: str, db: DB, current_user: CurrentUser):
    """Return a single ticket by UUID or human-readable number.

    Result is memoised in Redis under a per-ticket detail key.

    Returns:
        TicketOut: The requested ticket.

    Raises:
        HTTPException: **422** if the reference is malformed.
        HTTPException: **404** if the ticket does not exist.
    """
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
    """Apply a partial update to a ticket.

    Only the fields present in the request body are modified
    (`exclude_unset=True`). The service layer records a history entry per
    changed field and re-generates the embedding when title or description
    change. The list cache is invalidated on success.

    Returns:
        TicketOut: The updated ticket.
    """
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
    """Return the chronological audit trail of a ticket.

    Each entry records a field change (status, priority, assignee, etc.)
    together with the actor and timestamp.

    Returns:
        list: Ordered list of `TicketHistory` entries.
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    return await history_service.get_history(db, ticket.id)


@router.post("/{ticket_ref}/reply-draft", response_model=ReplyDraftResponse, summary="Generate an AI comment draft")
async def generate_reply_draft(
    ticket_ref: str,
    body: ReplyDraftRequest,
    db: DB,
    current_user: CurrentUser,
):
    """Generate an AI-written reply draft for the ticket.

    The whole call is wrapped in an `AIRunTracker` so that token usage,
    latency, cost and the provider/model actually used are persisted as an
    `AIRun` row. The active provider is chosen from the request body
    (`openai`, `google` or `auto`), and the model defaults align with the
    project's configured primary provider when `auto` is requested.

    Args:
        ticket_ref: Ticket UUID or short number from the URL path.
        body: Request payload with optional `resolution_note` and
            `preferred_provider`.
        db: Async SQLAlchemy session.
        current_user: Authenticated user authoring the draft.

    Returns:
        ReplyDraftResponse: The generated draft text plus the `ai_run_id`
        identifying the metrics row.

    Raises:
        HTTPException: **502** if the LLM provider fails. The error is
        recorded in the corresponding `AIRun` before being re-raised.
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
    """Permanently delete a ticket. Only its author is authorised.

    On success, broadcasts a `TICKET_DELETED` WebSocket event and notifies
    any user that had interacted with the ticket.

    Raises:
        HTTPException: **403** if the caller is not the ticket's author.
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    if ticket.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this ticket."
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
    """Notify the author that another user is requesting the ticket's deletion.

    Used when a non-author wants the ticket removed: instead of granting
    delete privileges, the system sends an in-app notification to the
    author so they can act on it.

    Returns:
        dict: `{"ok": True}` on success.

    Raises:
        HTTPException: **400** if the caller is the ticket's author
            (authors should call `DELETE` directly).
    """
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


@router.get("/{ticket_ref}/diagnosis", summary="Stream AI diagnosis (SSE)")
async def get_diagnosis(
    ticket_ref: str,
    db: DB,
    current_user: CurrentUser,
    preferred_provider: str | None = None,
):
    """Stream an AI-generated diagnosis of the ticket as Server-Sent Events.

    The diagnosis is produced by `ai_copilot_service.stream_ticket_diagnosis`,
    which runs the RAG pipeline (ticket context + knowledge-base chunks) and
    streams incremental tokens. Each chunk is emitted as an SSE `data:` line.
    The associated `AIRun` is finalised in a `finally` block so cost and
    token metrics are persisted even if the client disconnects mid-stream.

    Args:
        ticket_ref: Ticket UUID or short number.
        db: Async SQLAlchemy session.
        current_user: Authenticated requester.
        preferred_provider: Optional override (`openai`, `google` or `auto`).

    Returns:
        StreamingResponse: `text/event-stream` response.
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
        # First event carries the AIRun id so the frontend can later attach
        # feedback to this specific run.
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


@router.get("/{ticket_ref}/web-context", summary="Get scraped client web context")
async def get_ticket_web_context(
    ticket_ref: str,
    db: DB,
    current_user: CurrentUser,
):
    """Return the latest scraped web content associated to the ticket's client URL.

    Looks up the most recent `KnowledgeChunk` of type `client_web_context`
    that references this ticket and returns its raw text. Used by the
    frontend "client context" panel.

    Returns:
        dict: `{"content": str | None}` — `None` if no scrape has run yet.
    """
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


@router.post("/{ticket_ref}/web-scrape-refresh", summary="Trigger a background re-scrape")
async def refresh_ticket_web_scrape(
    ticket_ref: str,
    db: DB,
    current_user: CurrentUser,
):
    """Re-scrape the ticket's client URL and re-index it as knowledge.

    Fires a fire-and-forget `asyncio.create_task` so the HTTP request
    returns immediately while the scraping pipeline runs in the background.

    Returns:
        dict: `{"status": "scraping_started"}`.

    Raises:
        HTTPException: **400** if the ticket has no `client_url`.
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    if not ticket.client_url:
        raise HTTPException(status_code=400, detail="Ticket has no URL to scrape.")
    asyncio.create_task(scraping_service.scrape_and_index_url(ticket.id, ticket.client_url))
    return {"status": "scraping_started"}
