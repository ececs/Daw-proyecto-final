"""Threaded commentary validation structures.

Encapsulates business constraint validations and responses for ticket comments.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from .user import UserOut


class CommentCreate(BaseModel):
    """Input validation schema for appending commentary events.

    Enforces logical constraints prohibiting blank entries or excessive spacing.
    """
    content: str = Field(..., min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        """Ensures the commentary payload is not purely whitespace."""
        if not v.strip():
            raise ValueError("content must not be blank")
        return v.strip()


class CommentOut(BaseModel):
    """Serialized output schema documenting a specific threaded comment entry."""
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    created_at: datetime
    author: UserOut | None = None

    model_config = {"from_attributes": True}
