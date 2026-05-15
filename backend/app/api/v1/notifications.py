"""Real-time alerts and user notification state controller.

Aggregates historical notification lists and transactional state migrations
governing individual dismissal markers, hard deletions, and mass read resets.
"""

import uuid
from typing import List
from fastapi import APIRouter, HTTPException
from app.core.dependencies import CurrentUser, DB
from app.schemas.notification import NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationOut], summary="List my notifications")
async def list_notifications(current_user: CurrentUser, db: DB, limit: int = 50):
    """Retrieves chronologically sorted notifications addressing the active identity."""
    return await notification_service.list_notifications(
        db, user_id=current_user.id, limit=limit
    )


@router.patch("/{notification_id}/read", summary="Mark a notification as read")
async def mark_read(notification_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """Toggles targeted read flag states freeing pending notification counters.

    Raises:
        HTTPException (404): Returned if identifiers do not align with user context.
    """
    success = await notification_service.mark_read(
        db, notification_id=notification_id, user_id=current_user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.delete("/{notification_id}", summary="Delete a notification")
async def delete_notification(notification_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """Permanently prunes notification entities assigned to verifying identities.

    Raises:
        HTTPException (404): When targeting foreign or nonexistent alert entries.
    """
    success = await notification_service.delete_notification(
        db, notification_id=notification_id, user_id=current_user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.patch("/read-all", summary="Mark all notifications as read")
async def mark_all_read(current_user: CurrentUser, db: DB):
    """Resets the entire pending unread counter array scoped to caller sessions.

    Transmits global push synchronizers invalidating badge numbers across active tabs.
    """
    count = await notification_service.mark_all_read(db, user_id=current_user.id)
    await notification_service.broadcast_notifications_read_all(
        db, user_id=current_user.id, unread_count=0
    )
    return {"ok": True, "count": count}
