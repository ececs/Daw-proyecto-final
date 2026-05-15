"""Audit trail chronological tracking schemas.

Maps state transitions and user-driven mutations across system incidents.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel

from app.schemas.user import UserOut


class TicketHistoryOut(BaseModel):
    """Serialized output schema reflecting a single delta mutation log.

    Defines point-in-time captures storing prior values, new configurations,
    and the initiating administrative actor identities.
    """
    id: uuid.UUID
    ticket_id: uuid.UUID | None
    actor: UserOut | None = None
    field: str
    old_value: str | None
    new_value: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
