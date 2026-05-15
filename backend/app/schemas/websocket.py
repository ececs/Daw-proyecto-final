"""WebSocket real-time communications infrastructure schemas.

Contains internal enumerations for event-driven multiplexing across active
connection states and client distribution envelopes.
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid

class WSMessageType(str, Enum):
    """Allowed categorization types for real-time streaming payloads."""
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
    """Unified messaging envelope distributing real-time payloads to browsers.

    Standardizes standard message frames, supporting contextual ticket references
    and nested payload dictionaries for rich client-side state updates.
    """
    type: WSMessageType
    ticket_id: Optional[uuid.UUID] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)
