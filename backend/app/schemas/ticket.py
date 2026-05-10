import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.ticket import TicketStatus, TicketPriority
from .user import UserOut


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TicketPriority = TicketPriority.medium
    assignee_id: uuid.UUID | None = None
    client_url: str | None = None
    client_summary: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()


class TicketUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assignee_id: uuid.UUID | None = None
    client_url: str | None = None
    client_summary: str | None = None


class ReplyDraftRequest(BaseModel):
    resolution_note: str = Field(..., min_length=1, max_length=2000)
    preferred_provider: str | None = Field(default="auto")

    @field_validator("resolution_note")
    @classmethod
    def resolution_note_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("resolution_note must not be blank")
        return v.strip()

    @field_validator("preferred_provider")
    @classmethod
    def preferred_provider_valid(cls, v: str | None) -> str | None:
        if v is None:
            return "auto"
        if v not in {"auto", "openai", "google"}:
            raise ValueError("preferred_provider must be one of: auto, openai, google")
        return v


class ReplyDraftResponse(BaseModel):
    draft: str
    ai_run_id: uuid.UUID


class TicketOut(BaseModel):
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
    items: list[TicketOut]
    total: int
    page: int
    size: int
