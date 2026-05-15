"""Pydantic schemas for users."""

import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    """Public-facing user profile shape (used in every response that nests a user)."""
    id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
