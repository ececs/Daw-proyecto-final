"""Threaded commentary and ticket discussion management service.

Orchestrates commenting lifecycles including creation, contextual listing,
and secure actor-restricted deletions. Automatically dispatches transactional
notifications to related actors upon successful persistence.
"""

import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.comment import Comment
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.comment import CommentOut
from app.services import notification_service


async def list_comments(db: AsyncSession, ticket_id: uuid.UUID) -> List[CommentOut]:
    """Recovers a chronological sequence of comments linked to a specific ticket.

    Args:
        db: Active asynchronous SQLAlchemy transactional database session.
        ticket_id: The UUID key of the parent ticket being retrieved.

    Returns:
        List[CommentOut]: Collection of serialized comments sorted by creation date.
    """
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))  # type: ignore[attr-defined]
        .where(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return [CommentOut.model_validate(c) for c in comments]


async def create_comment(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    content: str,
    author: User,
) -> Optional[CommentOut]:
    """Creates a comment, persists it, and triggers side-effect notification flows.

    Verifies ticket existence, records transaction, dispatches real-time user
    notifications, and broadcasts update signals to frontend WebSocket clients.

    Args:
        db: Active asynchronous SQLAlchemy database session.
        ticket_id: UUID of the parent ticket.
        content: Raw text body of the commentary record.
        author: The User model representing the active commenter.

    Returns:
        Optional[CommentOut]: Validated output schema representation of new comment,
                              or None if the referenced parent ticket does not exist.
    """
    # 1. Verify ticket existence (needed for notification logic)
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    
    if not ticket:
        return None

    # 2. Create model
    comment = Comment(
        ticket_id=ticket_id,
        author_id=author.id,
        content=content,
    )
    db.add(comment)
    await db.flush()

    # 3. Trigger side effects
    await notification_service.notify_comment_added(
        db, ticket=ticket, commenter=author
    )
    # Broadcaster global update to refresh UI
    await notification_service.notify_ticket_updated(db, ticket=ticket, actor=author)

    # 4. Finalize
    await db.commit()
    
    # 5. Re-fetch with author relation for the schema
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))  # type: ignore[attr-defined]
        .where(Comment.id == comment.id)
    )
    return CommentOut.model_validate(result.scalar_one())


async def delete_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> bool:
    """Deletes a comment ensuring restricting operations strictly to the original author.

    Args:
        db: Active asynchronous SQLAlchemy database session.
        comment_id: Unique identifier of the target comment.
        actor_id: The unique UUID belonging to the attempting user.

    Returns:
        bool: True if deleted successfully, False if missing or unauthorized.
    """
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    
    if not comment or comment.author_id != actor_id:
        return False

    await db.delete(comment)
    await db.commit()
    return True
