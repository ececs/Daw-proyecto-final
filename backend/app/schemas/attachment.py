"""Pydantic schemas for attachments."""

import uuid
from datetime import datetime
from pydantic import BaseModel


class AttachmentOut(BaseModel):
    """Response shape for attachment metadata, including a presigned download URL."""
    id: uuid.UUID
    ticket_id: uuid.UUID
    uploader_id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    created_at: datetime
    download_url: str | None = None
    use_for_rag: bool = False

    model_config = {"from_attributes": True}
