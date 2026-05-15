"""Ticketing domain schemas and input validators.

Defines the foundational models for ticket instantiation, attribute mutation,
paginated list recovery, and automated reply draft requests.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.ticket import TicketStatus, TicketPriority
from .user import UserOut


def _normalize_client_url(value: str | None) -> str | None:
    """Normalize historical or manually-entered client URLs.

    Some tickets may store bare domains such as ``example.com``. We persist
    them as absolute HTTPS URLs so frontend rendering and background scraping
    behave consistently.
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
    """Input validation schema for creating a new ticket record.

    Asserts minimum and maximum constraints on textual identifiers and standardizes
    client URLs prior to persistent storage.
    """
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TicketPriority = TicketPriority.medium
    assignee_id: uuid.UUID | None = None
    client_url: str | None = None
    client_summary: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        """Ensures ticket title contains valid non-whitespace characters."""
        if not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()

    @field_validator("client_url")
    @classmethod
    def normalize_client_url(cls, v: str | None) -> str | None:
        """Triggers URL normalization to enforce schema protocols (HTTPS)."""
        return _normalize_client_url(v)


class TicketUpdate(BaseModel):
    """Validation schema for modifying existing ticket fields.

    Supports partial state updates (PATCH paradigm) allowing optional modifications
    across any combination of ticket properties.
    """
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
        """Ensures updated URL values maintain proper scheme formatting."""
        return _normalize_client_url(v)


class ReplyDraftRequest(BaseModel):
    """Input schema for triggering LLM-driven draft email resolutions.

    Captures core resolution context and preferred AI engine preferences.
    """
    resolution_note: str = Field(..., min_length=1, max_length=2000)
    preferred_provider: str | None = Field(default="auto")

    @field_validator("resolution_note")
    @classmethod
    def resolution_note_not_blank(cls, v: str) -> str:
        """Validates the baseline resolution reasoning is not blank."""
        if not v.strip():
            raise ValueError("resolution_note must not be blank")
        return v.strip()

    @field_validator("preferred_provider")
    @classmethod
    def preferred_provider_valid(cls, v: str | None) -> str | None:
        """Validates selected provider matches allowed platform enumerations."""
        if v is None:
            return "auto"
        if v not in {"auto", "openai", "google"}:
            raise ValueError("preferred_provider must be one of: auto, openai, google")
        return v


class ReplyDraftResponse(BaseModel):
    """Response wrapper encapsulating AI-generated resolutions and run trace keys."""
    draft: str
    ai_run_id: uuid.UUID


class TicketOut(BaseModel):
    """Serialized response schema presenting detailed Ticket state representations.

    Fully nests the associated Author and Assignee model models using internal
    SQLAlchemy attribute mappings.
    """
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
    """Standardized container pagination wrapper for discrete collections of TicketOut."""
    items: list[TicketOut]
    total: int
    page: int
    size: int
