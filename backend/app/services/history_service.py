"""Ticket audit-history service.

Append-only log of every field-level change on a ticket. Used both by the
UI (history tab) and by `ai_metrics_service` to compute time-to-close.
There are no update / delete helpers on purpose: the log is meant to be
immutable.
"""

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.ticket_history import TicketHistory
from app.schemas.ticket_history import TicketHistoryOut


async def record_change(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    actor_id: uuid.UUID,
    field: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    """Append a single audit entry. Uses `flush`, not `commit`.

    Letting the caller decide the transaction boundary keeps the history
    write atomic with the mutation it describes — both rows land together
    or neither does.

    Args:
        db: Async SQLAlchemy session.
        ticket_id: Ticket being audited.
        actor_id: User performing the change.
        field: Name of the modified field (e.g. `"status"`, `"priority"`).
        old_value: Previous value as a string, or `None`.
        new_value: New value as a string, or `None`.
    """
    entry = TicketHistory(
        ticket_id=ticket_id,
        actor_id=actor_id,
        field=field,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(entry)
    await db.flush()


async def get_history(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    limit: int = 100,
) -> list[TicketHistoryOut]:
    """Return the latest `limit` audit entries for a ticket, newest first.

    Eager-loads the actor relation to avoid N+1 queries when serialising
    the response.
    """
    result = await db.execute(
        select(TicketHistory)
        .options(selectinload(TicketHistory.actor))
        .where(TicketHistory.ticket_id == ticket_id)
        .order_by(TicketHistory.created_at.desc())
        .limit(limit)
    )
    return [TicketHistoryOut.model_validate(h) for h in result.scalars().all()]
