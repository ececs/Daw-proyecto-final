"""Attachment database model mapping.

Handles file upload tracking, associating object storage references (MinIO/R2)
with parent ticketing objects to facilitate binary and document attachments.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Attachment(Base):
    """Represents an uploaded file object associated with a support ticket.

    Stores file metadata including system MIME types, byte sizes, direct cloud
    storage access keys, and explicit toggles defining utilization scope for the
    automated RAG injection layers of the AI Assistant.
    """

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    use_for_rag: Mapped[bool] = mapped_column(default=False)
