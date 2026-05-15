"""Notifications endpoints.

Per-user notification feed used by the bell icon in the frontend. Supports
listing, marking a single notification as read, deleting a notification and
marking all of the current user's notifications as read at once.
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
    """Return the most recent notifications for the current user.

    Args:
        limit: Maximum number of notifications to return (default 50).

    Returns:
        list[NotificationOut]: Notifications ordered from newest to oldest.
    """
    return await notification_service.list_notifications(
        db, user_id=current_user.id, limit=limit
    )


@router.patch("/{notification_id}/read", summary="Mark a notification as read")
async def mark_read(notification_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """Mark a single notification belonging to the current user as read.

    Returns:
        dict: `{"ok": True}` on success.

    Raises:
        HTTPException: **404** if the notification does not exist or does
            not belong to the current user.
    """
    success = await notification_service.mark_read(
        db, notification_id=notification_id, user_id=current_user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.delete("/{notification_id}", summary="Delete a notification")
async def delete_notification(notification_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """Delete a notification belonging to the current user.

    Returns:
        dict: `{"ok": True}` on success.

    Raises:
        HTTPException: **404** if the notification does not exist or does
            not belong to the current user.
    """
    success = await notification_service.delete_notification(
        db, notification_id=notification_id, user_id=current_user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.patch("/read-all", summary="Mark all notifications as read")
async def mark_all_read(current_user: CurrentUser, db: DB):
    """Mark every notification of the current user as read.

    After updating the rows, broadcasts a WebSocket event so any other
    tab/device the user has open zeroes its badge in real time.

    Returns:
        dict: `{"ok": True, "count": <number of rows updated>}`.
    """
    count = await notification_service.mark_all_read(db, user_id=current_user.id)
    await notification_service.broadcast_notifications_read_all(
        db, user_id=current_user.id, unread_count=0
    )
    return {"ok": True, "count": count}
