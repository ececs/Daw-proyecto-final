"""
Comment routes — Nested under /api/v1/tickets/{ticket_number}/comments.
"""

import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from app.core.dependencies import CurrentUser, DB
from app.schemas.comment import CommentCreate, CommentOut
from app.services import comment_service, ticket_service

router = APIRouter(prefix="/tickets", tags=["Comments"])


@router.get(
    "/{ticket_number}/comments",
    response_model=List[CommentOut],
    summary="List comments on a ticket",
)
async def list_comments(ticket_number: int, db: DB, current_user: CurrentUser):
    ticket = await ticket_service.get_ticket_by_number(db, ticket_number)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return await comment_service.list_comments(db, ticket.id)


@router.post(
    "/{ticket_number}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a ticket",
)
async def create_comment(
    ticket_number: int,
    body: CommentCreate,
    db: DB,
    current_user: CurrentUser,
):
    ticket = await ticket_service.get_ticket_by_number(db, ticket_number)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    comment = await comment_service.create_comment(
        db, ticket_id=ticket.id, content=body.content, author=current_user
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return comment


@router.delete(
    "/{ticket_number}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
)
async def delete_comment(
    ticket_number: int,
    comment_id: uuid.UUID,
    db: DB,
    current_user: CurrentUser,
):
    ticket = await ticket_service.get_ticket_by_number(db, ticket_number)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    success = await comment_service.delete_comment(
        db, comment_id=comment_id, actor_id=current_user.id
    )
    if not success:
        from sqlalchemy import select
        from app.models.comment import Comment
        exists = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="Comment not found")
        raise HTTPException(status_code=403, detail="You can only delete your own comments")

    from app.services import notification_service
    await notification_service.notify_ticket_updated(db, ticket=ticket, actor=current_user)
