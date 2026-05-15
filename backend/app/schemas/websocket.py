"""Pydantic schemas for the WebSocket transport layer."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid


class WSMessageType(str, Enum):
    """Discriminator used by the frontend to dispatch incoming events."""
    NOTIFICATION = "notification"
    NOTIFICATION_DELETED = "notification_deleted"
    NOTIFICATION_READ = "notification_read"
    NOTIFICATIONS_READ_ALL = "notifications_read_all"
    WEB_SCRAPE_COMPLETED = "web_scrape_completed"
    TICKET_UPDATED = "ticket_updated"
    TICKET_CREATED = "ticket_created"
    TICKET_DELETED = "ticket_deleted"
    SYSTEM_ALERT = "system_alert"


class WSMessage(BaseModel):
    """Envelope for every message sent over the WebSocket.

    The `type` field is mandatory and drives client-side dispatch; `data`
    carries the type-specific payload as a free-form dict. `ticket_id`
    is hoisted out for convenience because the UI routes most messages
    to the right ticket view based on it.
    """
    type: WSMessageType
    ticket_id: Optional[uuid.UUID] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)
