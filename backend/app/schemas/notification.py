"""Notification routing delivery schemas.

Contains validation boundaries for internal notifications and streaming Pub/Sub.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.notification import NotificationType

from typing import Optional

class NotificationOut(BaseModel):
    """Serialized output schema representing localized backend notifications."""
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    ticket_id: Optional[uuid.UUID]
    message: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPayload(BaseModel):
    """Serialized delivery schema intended for active real-time WebSocket streams.

    Encapsulates payload packets synchronized over Postgres LISTEN/NOTIFY buffers,
    distributing counters and discrete JSON events to frontend clients.
    """
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    ticket_id: Optional[uuid.UUID]
    message: str
    created_at: str
    unread_count: int | None = None
