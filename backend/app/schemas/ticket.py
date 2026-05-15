"""Pydantic schemas for the ticket API.

Defines the request bodies (`TicketCreate`, `TicketUpdate`,
`ReplyDraftRequest`) and the response shapes (`TicketOut`,
`TicketListResponse`, `ReplyDraftResponse`).
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.ticket import TicketStatus, TicketPriority
from .user import UserOut


def _normalize_client_url(value: str | None) -> str | None:
    """Normalise historical / hand-typed client URLs to absolute HTTPS form.

    Some legacy tickets store bare domains like ``example.com``; we
    promote them to ``https://example.com`` so frontend rendering and
    background scraping have a consistent shape to work with.
    """
    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    if "://" not in trimmed:
        return f"https://{trimmed}"
    return trimmed


class TicketCreate(BaseModel):
    """Body of `POST /tickets`."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TicketPriority = TicketPriority.medium
    assignee_id: uuid.UUID | None = None
    client_url: str | None = None
    client_summary: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        """Reject whitespace-only titles."""
        if not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()

    @field_validator("client_url")
    @classmethod
    def normalize_client_url(cls, v: str | None) -> str | None:
        """Promote bare domains to absolute HTTPS URLs."""
        return _normalize_client_url(v)


class TicketUpdate(BaseModel):
    """Body of `PATCH /tickets/{ref}` — every field is optional."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assignee_id: uuid.UUID | None = None
    client_url: str | None = None
    client_summary: str | None = None

    @field_validator("client_url")
    @classmethod
    def normalize_client_url(cls, v: str | None) -> str | None:
        """Promote bare domains to absolute HTTPS URLs."""
        return _normalize_client_url(v)


class ReplyDraftRequest(BaseModel):
    """Body of `POST /tickets/{ref}/reply-draft`."""
    resolution_note: str = Field(..., min_length=1, max_length=2000)
    preferred_provider: str | None = Field(default="auto")

    @field_validator("resolution_note")
    @classmethod
    def resolution_note_not_blank(cls, v: str) -> str:
        """Reject whitespace-only resolution notes."""
        if not v.strip():
            raise ValueError("resolution_note must not be blank")
        return v.strip()

    @field_validator("preferred_provider")
    @classmethod
    def preferred_provider_valid(cls, v: str | None) -> str | None:
        """Restrict the override to the supported provider keys."""
        if v is None:
            return "auto"
        if v not in {"auto", "openai", "google"}:
            raise ValueError("preferred_provider must be one of: auto, openai, google")
        return v


class ReplyDraftResponse(BaseModel):
    """Response shape for `POST /tickets/{ref}/reply-draft`."""
    draft: str
    ai_run_id: uuid.UUID


class TicketOut(BaseModel):
    """Response shape for a ticket, with author and assignee eager-loaded."""
    id: uuid.UUID
    ticket_number: int
    title: str
    description: str | None
    status: TicketStatus
    priority: TicketPriority
    author_id: uuid.UUID
    assignee_id: uuid.UUID | None
    client_url: str | None = None
    client_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    author: UserOut | None = None
    assignee: UserOut | None = None

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    """Paginated response wrapper for `GET /tickets`."""
    items: list[TicketOut]
    total: int
    page: int
    size: int
