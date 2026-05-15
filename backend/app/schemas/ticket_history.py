"""Pydantic schemas for the ticket audit history endpoint."""

import uuid
from datetime import datetime
from pydantic import BaseModel

from app.schemas.user import UserOut


class TicketHistoryOut(BaseModel):
    """Response shape for one row of a ticket's audit trail."""
    id: uuid.UUID
    ticket_id: uuid.UUID | None
    actor: UserOut | None = None
    field: str
    old_value: str | None
    new_value: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
