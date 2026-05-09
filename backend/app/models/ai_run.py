import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AIRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    surface: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    tool_actions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rag_queries_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rag_hits_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    estimated_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)

    user = relationship("User", foreign_keys=[user_id], lazy="noload")
    feedback_entries: Mapped[list["AIFeedback"]] = relationship(  # type: ignore[name-defined]
        "AIFeedback",
        back_populates="ai_run",
        cascade="all, delete-orphan",
        lazy="noload",
    )
