"""Append-only audit trail management service.

Persists point-in-time snapshots tracking property deltas triggered by system mutation events.
Maintains a historical integrity boundary by disallowing internal deletions or updates.
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
    """Appends a single delta mutation log to the ticket's audit history trail.

    Args:
        db: Active asynchronous SQLAlchemy transactional session.
        ticket_id: The UUID key of the target ticket being audited.
        actor_id: The UUID identification key of the user driving the mutation.
        field: Textual field name undergoing state modification.
        old_value: Text string of the prior value before mutation.
        new_value: Text string of the new state value after committing.
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
    """Retrieves chronological change records associated with a single ticket.

    Uses eager loading for the associated Actor profile to minimize N+1 queries.

    Args:
        db: Active asynchronous SQLAlchemy database session.
        ticket_id: Unique UUID reference for the targeted ticket history.
        limit: Constraints the maximum return size of the query array.

    Returns:
        list[TicketHistoryOut]: Serialized audit logs sorted in descending order.
    """
    result = await db.execute(
        select(TicketHistory)
        .options(selectinload(TicketHistory.actor))
        .where(TicketHistory.ticket_id == ticket_id)
        .order_by(TicketHistory.created_at.desc())
        .limit(limit)
    )
    return [TicketHistoryOut.model_validate(h) for h in result.scalars().all()]
