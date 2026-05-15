"""Comment service.

CRUD on the `Comment` aggregate with the associated notification fan-out:
when a comment is created, both the ticket author and the assignee
receive a personal notification and a `TICKET_UPDATED` event is
broadcast so other clients refresh the conversation view.
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
    """Return every comment of a ticket ordered from oldest to newest.

    Args:
        db: Async SQLAlchemy session.
        ticket_id: Parent ticket primary key.

    Returns:
        list[CommentOut]: Comments with their author eager-loaded.
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
    """Create a comment on a ticket and fan out the associated events.

    Performs an existence check on the parent ticket, persists the
    comment, notifies subscribers (author + assignee), broadcasts a
    `TICKET_UPDATED` event for the UI, and finally returns the comment
    re-fetched with its `author` relation eager-loaded so the response
    schema validates without extra round trips.

    Args:
        db: Async SQLAlchemy session.
        ticket_id: Parent ticket primary key.
        content: Comment body.
        author: User authoring the comment.

    Returns:
        CommentOut | None: The persisted comment, or `None` if the parent
        ticket does not exist.
    """
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        return None

    comment = Comment(
        ticket_id=ticket_id,
        author_id=author.id,
        content=content,
    )
    db.add(comment)
    await db.flush()

    await notification_service.notify_comment_added(
        db, ticket=ticket, commenter=author
    )
    await notification_service.notify_ticket_updated(db, ticket=ticket, actor=author)

    await db.commit()

    # Why: re-fetch with `selectinload(Comment.author)` so the Pydantic
    # response schema can serialize the author without lazy-loading on
    # an already-closed transaction.
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
    """Delete a comment if the actor is its author.

    Returns:
        bool: `True` on success; `False` if the comment does not exist or
        the actor is not its author. The router layer is responsible for
        translating `False` into the appropriate 404 vs. 403 status.
    """
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment or comment.author_id != actor_id:
        return False

    await db.delete(comment)
    await db.commit()
    return True
