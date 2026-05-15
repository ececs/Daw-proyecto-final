"""Artificial Intelligence telemetry operational schemas.

Defines payload structures for user-submitted reinforcement learning feedback
and system-aggregated financial/accuracy summaries.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AIFeedbackCreate(BaseModel):
    """Input schema for submitting user evaluation on a discrete AI execution.

    Supports storing discrete tags (labels) and rich-text user summaries.
    """
    ai_run_id: uuid.UUID
    helped: bool
    label: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=1000)


class AIRunStatsSummary(BaseModel):
    """Analytical summary mapping global system performance and token consumption.

    Aggregates hit rates, average cost distributions, and system-wide conversion
    metrics reflecting business outcomes across historical executions.
    """
    total_runs: int
    runs_by_surface: dict[str, int]
    success_rate: float
    fallback_rate: float
    total_rag_queries: int
    rag_hit_rate: float
    positive_feedback_count: int
    negative_feedback_count: int
    helped_rate: float
    tickets_closed_with_ai: int
    tickets_closed_without_ai: int
    avg_time_to_close_with_ai_hours: float | None
    avg_time_to_close_without_ai_hours: float | None
    total_estimated_cost_usd: float
    avg_cost_per_run_usd: float
    avg_cost_per_ticket_with_ai_usd: float


class AITicketStats(BaseModel):
    """Discrete telemetry footprint mapping AI assistance on a specific ticket.

    Accumulates operational costs, diagnosis iterations, and reinforcement logs
    scoped strictly to single incident identifiers.
    """
    ticket_id: uuid.UUID
    diagnosis_runs: int
    chat_runs: int
    rag_queries_count: int
    rag_hit_rate: float
    last_ai_used_at: datetime | None
    positive_feedback_count: int
    negative_feedback_count: int
    helped: bool | None
    first_closed_at: datetime | None
    time_to_close_hours: float | None
    estimated_cost_usd: float
