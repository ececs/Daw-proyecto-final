"""Ticket comments endpoints.

Routes nested under `/tickets/{ticket_ref}/comments` for listing, creating
and deleting comments attached to a ticket.
"""

import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from app.core.dependencies import CurrentUser, DB
from app.schemas.comment import CommentCreate, CommentOut
from app.services import comment_service, ticket_service

router = APIRouter(prefix="/tickets", tags=["Comments"])


async def _resolve_ticket_or_raise(db: DB, ticket_ref: str):
    """Resolve a ticket reference or raise an HTTP error.

    Validates the format of `ticket_ref` (UUID or short number) and loads
    the parent ticket before any comment operation runs against it.

    Returns:
        Ticket: The resolved ticket.

    Raises:
        HTTPException: **422** for malformed references, **404** if the
            ticket does not exist.
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


@router.get(
    "/{ticket_ref}/comments",
    response_model=List[CommentOut],
    summary="List comments on a ticket",
)
async def list_comments(ticket_ref: str, db: DB, current_user: CurrentUser):
    """Return every comment of the ticket in chronological order.

    Returns:
        list[CommentOut]: Comments sorted from oldest to newest.
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    return await comment_service.list_comments(db, ticket.id)


@router.post(
    "/{ticket_ref}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a ticket",
)
async def create_comment(
    ticket_ref: str,
    body: CommentCreate,
    db: DB,
    current_user: CurrentUser,
):
    """Create a new comment authored by the current user.

    Returns:
        CommentOut: The persisted comment.

    Raises:
        HTTPException: **404** if the ticket disappears between the
            reference check and the service call (race condition guard).
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)
    comment = await comment_service.create_comment(
        db, ticket_id=ticket.id, content=body.content, author=current_user
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return comment


@router.delete(
    "/{ticket_ref}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
)
async def delete_comment(
    ticket_ref: str,
    comment_id: uuid.UUID,
    db: DB,
    current_user: CurrentUser,
):
    """Delete a comment. Only its author is authorised.

    On success, notifies subscribers of the parent ticket so their views
    stay in sync.

    Raises:
        HTTPException: **404** if the comment does not exist.
        HTTPException: **403** if the caller is not the comment's author.
    """
    ticket = await _resolve_ticket_or_raise(db, ticket_ref)

    success = await comment_service.delete_comment(
        db, comment_id=comment_id, actor_id=current_user.id
    )
    if not success:
        # Why: the service returns False both for "not found" and "forbidden";
        # disambiguate here so the API responds with the correct status code.
        from sqlalchemy import select
        from app.models.comment import Comment
        exists = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="Comment not found")
        raise HTTPException(status_code=403, detail="You can only delete your own comments")

    from app.services import notification_service
    await notification_service.notify_ticket_updated(db, ticket=ticket, actor=current_user)
