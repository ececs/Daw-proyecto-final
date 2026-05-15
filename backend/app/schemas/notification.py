"""Pydantic schemas for notifications."""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.notification import NotificationType

from typing import Optional


class NotificationOut(BaseModel):
    """Response shape for a notification row."""
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    ticket_id: Optional[uuid.UUID]
    message: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPayload(BaseModel):
    """Envelope used when forwarding a notification over WebSocket / Pub/Sub.

    Carries the canonical notification fields plus the recipient's current
    `unread_count` so the badge in the UI can update in one round trip.
    """
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    ticket_id: Optional[uuid.UUID]
    message: str
    created_at: str
    unread_count: int | None = None
