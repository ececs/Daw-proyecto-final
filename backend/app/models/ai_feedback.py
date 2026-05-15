"""AI Agent execution user feedback database model mapping.

Enables active human-in-the-loop learning by allowing users to grade specific
agent executions with boolean utility toggles and textual annotations.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AIFeedback(Base):
    """Represents a subjective performance evaluation left by a user on an AI run.

    Applies strict unique constraints ensuring a single feedback record per user per run,
    facilitating reliable analytics and continuous reinforcement profiling.
    """

    __tablename__ = "ai_feedback"
    __table_args__ = (
        UniqueConstraint("ai_run_id", "user_id", name="uq_ai_feedback_run_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ai_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    helped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    ai_run = relationship("AIRun", back_populates="feedback_entries", lazy="noload")
    user = relationship("User", foreign_keys=[user_id], lazy="noload")
