"""Ticket business logic.

Owns the ticket lifecycle: validation of references, hybrid search,
creation/update with cascading side effects (audit history, real-time
notifications, cache invalidation and background embedding/scraping
tasks). All API routes that mutate or read tickets eventually call into
this module so the side-effect ordering stays in one place.
"""

import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sqlalchemy import case, func
from app.models.ticket import Ticket, TicketStatus, TicketPriority
from app.models.user import User
from app.schemas.ticket import TicketOut
import asyncio
import logging
from . import notification_service, embedding_service, scraping_service, cache_service, history_service


def is_valid_ticket_ref(ref: str) -> bool:
    """Return True if `ref` is a valid ticket reference.

    A reference is valid when it is either a positive integer (matching
    the human-readable `ticket_number`) or a UUID string (matching the
    canonical `id`).
    """
    try:
        int(ref)
        return True
    except ValueError:
        pass

    try:
        uuid.UUID(ref)
        return True
    except ValueError:
        return False


async def hybrid_search_tickets(
    db: AsyncSession,
    base_query,
    search: str,
    pool: int = 100,
) -> list[Ticket]:
    """Rank tickets by Reciprocal Rank Fusion of semantic and keyword results.

    Runs two independent queries against `base_query`:

    - A **semantic** query ordering by pgvector cosine distance between
      the ticket embedding and the embedding of `search`.
    - A **keyword** query matching `search` against `title` and
      `description` with `ILIKE`.

    Both result sets are merged using RRF (`1 / (rank + K)`, with `K = 60`)
    so neither signal alone dominates the ranking. When the embedding
    backend is unavailable, the function transparently falls back to the
    keyword-only ranking.

    Args:
        db: Async SQLAlchemy session.
        base_query: Pre-filtered `Select` to apply the search on top of.
        search: User-supplied search text.
        pool: Maximum candidates considered per signal before fusion.

    Returns:
        list[Ticket]: Tickets sorted by descending RRF score.
    """
    from app.services.embedding_service import generate_embedding

    pattern = f"%{search}%"
    K = 60

    search_embedding = await generate_embedding(search, task_type="RETRIEVAL_QUERY")
    # Why: exact title matches always outrank partial matches, regardless
    # of how SQLAlchemy chooses to order the secondary `updated_at` key.
    keyword_rank = case(
        (func.lower(Ticket.title) == search.lower(), 0),
        (Ticket.title.ilike(pattern), 1),
        else_=2,
    )

    if search_embedding is not None:
        sem_q = (
            base_query.where(Ticket.embedding.isnot(None))  # type: ignore[attr-defined]
            .order_by(Ticket.embedding.cosine_distance(search_embedding))  # type: ignore[attr-defined]
            .limit(pool)
        )
        kw_q = (
            base_query.where(Ticket.title.ilike(pattern) | Ticket.description.ilike(pattern))
            .order_by(keyword_rank, Ticket.updated_at.desc())
            .limit(pool)
        )

        sem_rows = (await db.execute(sem_q)).scalars().all()
        kw_rows = (await db.execute(kw_q)).scalars().all()

        rrf: dict = {}
        for i, t in enumerate(sem_rows):
            rrf[t.id] = rrf.get(t.id, 0.0) + 1.0 / (i + K)
        for i, t in enumerate(kw_rows):
            rrf[t.id] = rrf.get(t.id, 0.0) + 1.0 / (i + K)

        ticket_map = {t.id: t for t in (*sem_rows, *kw_rows)}
        ranked = sorted(rrf, key=rrf.__getitem__, reverse=True)
        return [ticket_map[i] for i in ranked]

    kw_q = (
        base_query.where(Ticket.title.ilike(pattern) | Ticket.description.ilike(pattern))
        .order_by(keyword_rank, Ticket.updated_at.desc())
        .limit(pool)
    )
    return list((await db.execute(kw_q)).scalars().all())


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> Optional[TicketOut]:
    """Fetch a single ticket by UUID with author and assignee eager-loaded.

    Args:
        db: Async SQLAlchemy session.
        ticket_id: Primary key of the ticket.

    Returns:
        TicketOut | None: Validated Pydantic representation, or `None` if
        the ticket does not exist.
    """
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.author),    # type: ignore[attr-defined]
            selectinload(Ticket.assignee),  # type: ignore[attr-defined]
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        return None

    return TicketOut.model_validate(ticket)


async def get_ticket_by_number(db: AsyncSession, number: int) -> Optional[Ticket]:
    """Fetch a ticket by its human-readable `ticket_number`."""
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.author),    # type: ignore[attr-defined]
            selectinload(Ticket.assignee),  # type: ignore[attr-defined]
        )
        .where(Ticket.ticket_number == number)
    )
    return result.scalar_one_or_none()


async def resolve_ticket(db: AsyncSession, ref: str) -> Optional[Ticket]:
    """Resolve a ticket from either a numeric number or a UUID string.

    Tries the numeric path first (because all human-typed references in
    the UI use that form) and falls back to UUID resolution.

    Returns:
        Ticket | None: The resolved ORM instance, or `None`.
    """
    _opts = [
        selectinload(Ticket.author),    # type: ignore[attr-defined]
        selectinload(Ticket.assignee),  # type: ignore[attr-defined]
    ]
    try:
        number = int(ref)
        result = await db.execute(select(Ticket).options(*_opts).where(Ticket.ticket_number == number))
        return result.scalar_one_or_none()
    except ValueError:
        pass
    try:
        uid = uuid.UUID(ref)
        result = await db.execute(select(Ticket).options(*_opts).where(Ticket.id == uid))
        return result.scalar_one_or_none()
    except ValueError:
        return None


async def create_ticket(
    db: AsyncSession,
    title: str,
    description: Optional[str],
    priority: TicketPriority,
    author_id: uuid.UUID,
    assignee_id: Optional[uuid.UUID] = None,
    client_url: Optional[str] = None,
    client_summary: Optional[str] = None,
) -> TicketOut:
    """Create a ticket and run all the associated side effects.

    The ticket row is persisted first so the rest of the operations (audit
    entry, notifications, WebSocket broadcast, cache invalidation, async
    embedding/scraping) have a stable id to reference. The embedding and
    URL scraping are dispatched as background tasks because they involve
    external services and must not block the HTTP response.

    Returns:
        TicketOut: The freshly created ticket, eager-loaded.
    """
    ticket = Ticket(
        title=title,
        description=description,
        priority=priority,
        author_id=author_id,
        assignee_id=assignee_id,
        client_url=client_url,
        client_summary=client_summary,
    )
    db.add(ticket)
    await db.flush()

    author_result = await db.execute(select(User).where(User.id == author_id))
    author = author_result.scalar_one()

    await db.commit()

    await history_service.record_change(db, ticket.id, author_id, "created", None, None)
    await db.commit()

    from app.schemas.websocket import WSMessageType
    await notification_service.notify_ticket_created(db, ticket=ticket, actor=author)
    await notification_service.broadcast_global_event(
        type=WSMessageType.TICKET_CREATED,
        data={"id": str(ticket.id), "ticket_number": ticket.ticket_number, "title": ticket.title},
        db=db
    )
    await db.commit()
    await cache_service.cache_invalidate_prefix("tickets:")

    asyncio.create_task(generate_ticket_embedding_task(ticket.id, title, description))
    if client_url:
        asyncio.create_task(scraping_service.scrape_and_index_url(ticket.id, client_url))

    return await get_ticket(db, ticket.id) # type: ignore


async def generate_ticket_embedding_task(ticket_id: uuid.UUID, title: str, description: Optional[str]) -> None:
    """Compute and persist the ticket embedding in an isolated session.

    Designed to be scheduled via `asyncio.create_task` after the request
    has returned. Uses its own SQLAlchemy session so a failure here cannot
    poison the caller's transaction; errors are logged with `exc_info`.
    """
    embedding = await embedding_service.generate_ticket_embedding(title, description)
    if embedding is None:
        return

    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = result.scalar_one_or_none()
            if ticket:
                ticket.embedding = embedding
                await session.commit()
                logging.getLogger(__name__).info(f"Ticket Service: Persistent embedding for ticket {ticket_id}")
    except Exception as exc:
        logging.getLogger(__name__).error(
            f"Ticket Service: Failed to persist embedding for {ticket_id}: {str(exc)}",
            exc_info=True
        )


async def update_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    update_data: dict,
    actor: User,
) -> Optional[TicketOut]:
    """Apply a partial update and emit fine-grained audit + notification events.

    For every changed field, a `TicketHistory` row is recorded with the
    old and new value (description changes only record the fact of the
    change, not the body). Status, priority and assignee changes also
    trigger dedicated notifications. When `title` or `description` change,
    a background task regenerates the embedding; when `client_url`
    changes, a background re-scrape is dispatched.

    Returns:
        TicketOut | None: The updated ticket, or `None` if it did not exist.
    """
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        return None

    old_status = ticket.status
    old_assignee_id = ticket.assignee_id
    old_priority = ticket.priority
    old_title = ticket.title
    old_description = ticket.description
    old_client_url = ticket.client_url

    for key, value in update_data.items():
        if hasattr(ticket, key):
            setattr(ticket, key, value)

    await db.flush()
    await db.commit()

    new_assignee: User | None = None
    if "assignee_id" in update_data and update_data["assignee_id"] != old_assignee_id:
        if update_data["assignee_id"]:
            res = await db.execute(select(User).where(User.id == update_data["assignee_id"]))
            new_assignee = res.scalar_one_or_none()

    if "status" in update_data and update_data["status"] != old_status:
        new_status_val = update_data["status"].value if hasattr(update_data["status"], "value") else str(update_data["status"])
        await history_service.record_change(db, ticket_id, actor.id, "status", old_status.value, new_status_val)

    if "priority" in update_data and update_data["priority"] != old_priority:
        new_priority_val = update_data["priority"].value if hasattr(update_data["priority"], "value") else str(update_data["priority"])
        await history_service.record_change(db, ticket_id, actor.id, "priority", old_priority.value, new_priority_val)

    if "title" in update_data and update_data["title"] != old_title:
        await history_service.record_change(db, ticket_id, actor.id, "title", old_title, update_data["title"])

    if "description" in update_data and update_data["description"] != old_description:
        await history_service.record_change(db, ticket_id, actor.id, "description", None, None)

    if "client_url" in update_data and update_data["client_url"] != old_client_url:
        await history_service.record_change(db, ticket_id, actor.id, "client_url", old_client_url, update_data["client_url"])

    if "assignee_id" in update_data and update_data["assignee_id"] != old_assignee_id:
        old_assignee_name: str | None = None
        if old_assignee_id:
            old_res = await db.execute(select(User).where(User.id == old_assignee_id))
            old_assignee_obj = old_res.scalar_one_or_none()
            old_assignee_name = old_assignee_obj.name if old_assignee_obj else None
        new_assignee_name = new_assignee.name if new_assignee else None
        await history_service.record_change(db, ticket_id, actor.id, "assignee", old_assignee_name, new_assignee_name)

    if "status" in update_data and update_data["status"] != old_status:
        await notification_service.notify_status_changed(
            db, ticket=ticket, actor=actor, new_status=update_data["status"]
        )

    if "priority" in update_data and update_data["priority"] != old_priority:
        await notification_service.notify_priority_changed(
            db, ticket=ticket, actor=actor, new_priority=update_data["priority"]
        )

    if "assignee_id" in update_data and update_data["assignee_id"] != old_assignee_id:
        if new_assignee:
            await notification_service.notify_ticket_assigned(
                db, ticket=ticket, assignee=new_assignee, actor=actor
            )

    await notification_service.notify_ticket_updated(db, ticket=ticket, actor=actor)
    await db.commit()
    await cache_service.cache_invalidate_prefix("tickets:")

    if "title" in update_data or "description" in update_data:
        new_title = update_data.get("title", ticket.title)
        new_desc = update_data.get("description", ticket.description)
        asyncio.create_task(generate_ticket_embedding_task(ticket_id, new_title, new_desc))

    if "client_url" in update_data and update_data["client_url"]:
        asyncio.create_task(scraping_service.scrape_and_index_url(ticket_id, update_data["client_url"]))

    return await get_ticket(db, ticket_id)
