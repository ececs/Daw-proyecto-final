"""AI usage telemetry and analytics service.

Persists one `AIRun` row per LLM-backed operation (chat, diagnosis, reply
draft, agent tool execution) plus optional `AIFeedback` rows when the
operator rates the result. The aggregation helpers expose dashboard-ready
metrics: success/fallback rates, RAG hit rate, estimated cost, and a
comparison of time-to-close for tickets that did or did not benefit from
AI assistance.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import observability
from app.core.config import settings
from app.models.ai_feedback import AIFeedback
from app.models.ai_run import AIRun
from app.models.ticket import Ticket
from app.models.ticket_history import TicketHistory

# Public pricing as of project freeze date (USD per 1 M tokens). Used only
# for cost *estimation*; the source of truth is each provider's invoice.
MODEL_PRICING_PER_MILLION = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-preview": {"input": 0.30, "output": 2.50},
}


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Return `dt` with an explicit UTC timezone, treating naive values as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def estimate_tokens(text: str | None) -> int:
    """Estimate the number of tokens in `text`.

    Uses the classic "≈4 characters per token" heuristic. This is good
    enough for cost estimation but should not be relied on for hard
    context-window limits.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of a call using `MODEL_PRICING_PER_MILLION`.

    Returns 0.0 when the model is not in the pricing table — typical for
    fallback or self-hosted models for which we do not bill the user.
    """
    pricing = MODEL_PRICING_PER_MILLION.get(model)
    if not pricing:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


def configured_primary_signature() -> tuple[str, str]:
    """Return the configured primary `(provider, model)` pair."""
    return settings.AI_PROVIDER, settings.AI_MODEL


def detect_provider_and_model(event_name: str | None) -> tuple[str, str]:
    """Infer the provider and model from a LangChain event name.

    Used during streaming to detect when the runtime silently switched to
    a fallback provider (e.g. Google when OpenAI is rate-limited).
    """
    name = event_name or ""
    lowered = name.lower()
    if "openai" in lowered:
        return "openai", "gpt-4o-mini"
    if "google" in lowered or "gemini" in lowered:
        return "google", "gemini-2.5-flash"
    return settings.AI_PROVIDER, settings.AI_MODEL


def normalize_rag_source(sources: set[str]) -> str:
    """Collapse a set of RAG source tags into a single label.

    - Empty / only `"none"` → `"none"`
    - Several distinct sources → `"mixed"`
    - Exactly one source → that source's name.
    """
    cleaned = {src for src in sources if src and src != "none"}
    if not cleaned:
        return "none"
    if len(cleaned) > 1:
        return "mixed"
    return next(iter(cleaned))


@dataclass
class AIRunTracker:
    """Mutable in-memory accumulator for a single AI run.

    Acts as a write-buffer for everything we want to persist in the
    `AIRun` row at the end of the request: token counts, RAG statistics,
    tool-action counters, fallback detection and latency. Decoupling this
    from the ORM model means call sites do not have to commit partial
    state mid-stream.
    """
    surface: str
    user_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    thread_id: str | None = None
    ai_run_id: uuid.UUID | None = None
    primary_provider: str = field(default_factory=lambda: settings.AI_PROVIDER)
    primary_model: str = field(default_factory=lambda: settings.AI_MODEL)
    provider: str = field(default_factory=lambda: settings.AI_PROVIDER)
    model: str = field(default_factory=lambda: settings.AI_MODEL)
    used_fallback: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tool_actions_count: int = 0
    rag_queries_count: int = 0
    rag_hits_count: int = 0
    rag_sources: set[str] = field(default_factory=set)
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: str | None = None

    def register_model(self, event_name: str | None) -> None:
        """Record the provider/model observed in an LLM event.

        If it differs from the primary configuration, sets `used_fallback`
        so the AIRun row reflects that a fallback path was taken.
        """
        observed_provider, observed_model = detect_provider_and_model(event_name)
        self.provider = observed_provider
        self.model = observed_model
        if observed_provider != self.primary_provider or observed_model != self.primary_model:
            self.used_fallback = True

    def add_tool_action(self) -> None:
        """Increment the counter of successful agent tool invocations."""
        self.tool_actions_count += 1

    def record_rag(self, queries: int, hits: int, source: str) -> None:
        """Accumulate one RAG retrieval round into the tracker."""
        self.rag_queries_count += max(0, queries)
        self.rag_hits_count += max(0, hits)
        if source:
            self.rag_sources.add(source)

    def append_output(self, text: str) -> None:
        """Add the estimated token count of `text` to `output_tokens`."""
        if text:
            self.output_tokens += estimate_tokens(text)

    @property
    def latency_ms(self) -> int:
        """Elapsed time since `started_at`, in milliseconds."""
        return int((datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000)

    @property
    def rag_source(self) -> str:
        """Single label summarising all RAG sources seen during the run."""
        return normalize_rag_source(self.rag_sources)


async def create_ai_run(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    surface: str,
    ticket_id: uuid.UUID | None,
    thread_id: str | None,
    provider: str | None = None,
    model: str | None = None,
    estimated_input_tokens: int | None = None,
) -> AIRun:
    """Insert an `AIRun` row in the "started" state and return it.

    The row starts with `success=False`; `finalize_ai_run` flips it once
    the request finishes successfully.
    """
    ai_run = AIRun(
        user_id=user_id,
        surface=surface,
        ticket_id=ticket_id,
        thread_id=thread_id,
        provider=provider or settings.AI_PROVIDER,
        model=model or settings.AI_MODEL,
        started_at=datetime.now(timezone.utc),
        success=False,
        estimated_input_tokens=estimated_input_tokens,
    )
    db.add(ai_run)
    await db.flush()
    return ai_run


async def finalize_ai_run(
    db: AsyncSession,
    ai_run: AIRun,
    tracker: AIRunTracker,
    *,
    success: bool,
    error_message: str | None = None,
) -> AIRun:
    """Persist the tracker into `ai_run` and emit observability metrics.

    Always called from a `try/finally` so the row reflects whether the
    request succeeded, even when the client disconnects mid-stream.
    """
    ai_run.provider = tracker.provider
    ai_run.model = tracker.model
    ai_run.used_fallback = tracker.used_fallback
    ai_run.completed_at = datetime.now(timezone.utc)
    ai_run.latency_ms = tracker.latency_ms
    ai_run.success = success
    ai_run.error_message = error_message
    ai_run.tool_actions_count = tracker.tool_actions_count
    ai_run.rag_queries_count = tracker.rag_queries_count
    ai_run.rag_hits_count = tracker.rag_hits_count
    ai_run.estimated_input_tokens = tracker.input_tokens or ai_run.estimated_input_tokens
    ai_run.estimated_output_tokens = tracker.output_tokens
    ai_run.estimated_cost_usd = estimate_cost_usd(
        tracker.model,
        ai_run.estimated_input_tokens or 0,
        tracker.output_tokens,
    )
    await db.commit()
    await db.refresh(ai_run)

    if tracker.used_fallback:
        observability.record_fallback()
    observability.record_rag(
        queries=tracker.rag_queries_count,
        hits=tracker.rag_hits_count,
        source=tracker.rag_source,
    )
    if success:
        observability.record_success(tracker.surface, ai_run.latency_ms, tracker.rag_source)
    else:
        observability.record_error(error_message or "Unknown AI error", tracker.surface)
    return ai_run


async def create_feedback(
    db: AsyncSession,
    *,
    ai_run_id: uuid.UUID,
    user_id: uuid.UUID,
    helped: bool,
    label: str | None = None,
    notes: str | None = None,
) -> AIFeedback:
    """Upsert the user's thumbs-up/down feedback for a given AIRun.

    Only one feedback per `(ai_run_id, user_id)` is allowed; subsequent
    calls overwrite the existing row.
    """
    existing = await db.execute(
        select(AIFeedback).where(
            AIFeedback.ai_run_id == ai_run_id,
            AIFeedback.user_id == user_id,
        )
    )
    feedback = existing.scalar_one_or_none()
    if feedback:
        feedback.helped = helped
        feedback.label = label
        feedback.notes = notes
    else:
        feedback = AIFeedback(
            ai_run_id=ai_run_id,
            user_id=user_id,
            helped=helped,
            label=label,
            notes=notes,
        )
        db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


async def _first_close_map(db: AsyncSession) -> dict[uuid.UUID, datetime]:
    """Return `{ticket_id: timestamp_of_first_close}` for every closed ticket.

    Used by both the global and per-ticket summaries to compute
    time-to-close — the *first* transition to `closed` is what counts,
    re-opens after that are ignored.
    """
    result = await db.execute(
        select(TicketHistory.ticket_id, func.min(TicketHistory.created_at))
        .where(
            TicketHistory.ticket_id.isnot(None),
            TicketHistory.field == "status",
            TicketHistory.new_value == "closed",
        )
        .group_by(TicketHistory.ticket_id)
    )
    return {
        ticket_id: ensure_utc(closed_at)
        for ticket_id, closed_at in result.all()
        if ticket_id and closed_at
    }


async def get_session_stats(
    db: AsyncSession, user_id: uuid.UUID, since: datetime
) -> dict:
    """Return per-user AI usage statistics since `since`.

    Drives the "AI activity" panel in the frontend session menu.
    """
    runs = (
        await db.execute(
            select(AIRun)
            .where(AIRun.user_id == user_id, AIRun.started_at >= since)
            .order_by(AIRun.started_at.desc())
        )
    ).scalars().all()

    chat_count = sum(1 for r in runs if r.surface == "chat")
    diagnoses_count = sum(1 for r in runs if r.surface == "diagnosis")
    action_count = sum(r.tool_actions_count or 0 for r in runs)
    success_count = sum(1 for r in runs if r.success)
    error_count = sum(1 for r in runs if not r.success and r.completed_at is not None)
    fallback_count = sum(1 for r in runs if r.used_fallback)
    rag_queries_count = sum(r.rag_queries_count or 0 for r in runs)
    rag_hits_count = sum(r.rag_hits_count or 0 for r in runs)

    latencies = [r.latency_ms for r in runs if r.success and r.latency_ms is not None]
    avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
    last_latency_ms = next((r.latency_ms for r in runs if r.latency_ms is not None), None)
    last_surface = runs[0].surface if runs else None

    last_error_run = next((r for r in runs if not r.success and r.error_message), None)
    last_error = last_error_run.error_message if last_error_run else None
    last_error_at = ensure_utc(last_error_run.completed_at or last_error_run.started_at) if last_error_run else None

    return {
        "chat_count": chat_count,
        "diagnoses_count": diagnoses_count,
        "action_count": action_count,
        "success_count": success_count,
        "error_count": error_count,
        "fallback_count": fallback_count,
        "rag_queries_count": rag_queries_count,
        "rag_hits_count": rag_hits_count,
        "avg_latency_ms": avg_latency_ms,
        "last_latency_ms": last_latency_ms,
        "last_surface": last_surface,
        "last_error": last_error,
        "last_error_at": last_error_at.isoformat() if last_error_at else None,
    }


async def get_stats_summary(db: AsyncSession) -> dict:
    """Return the global AI metrics dashboard.

    Aggregates every `AIRun` and `AIFeedback` row plus a comparison of
    time-to-close between tickets that received AI assistance before
    being closed and those that did not.
    """
    runs = (await db.execute(select(AIRun))).scalars().all()
    feedback_rows = (await db.execute(select(AIFeedback))).scalars().all()
    tickets = (await db.execute(select(Ticket))).scalars().all()
    first_close = await _first_close_map(db)

    total_runs = len(runs)
    runs_by_surface = {
        "chat": sum(1 for run in runs if run.surface == "chat"),
        "diagnosis": sum(1 for run in runs if run.surface == "diagnosis"),
        "reply_draft": sum(1 for run in runs if run.surface == "reply_draft"),
    }
    success_count = sum(1 for run in runs if run.success)
    fallback_count = sum(1 for run in runs if run.used_fallback)
    total_rag_queries = sum(run.rag_queries_count for run in runs)
    total_rag_hits = sum(run.rag_hits_count for run in runs)
    positive_feedback = sum(1 for fb in feedback_rows if fb.helped)
    negative_feedback = sum(1 for fb in feedback_rows if not fb.helped)
    total_cost = float(sum(Decimal(run.estimated_cost_usd or 0) for run in runs))

    closed_with_ai = 0
    closed_without_ai = 0
    close_with_ai_hours: list[float] = []
    close_without_ai_hours: list[float] = []
    ai_ticket_costs: dict[uuid.UUID, float] = {}
    runs_by_ticket: dict[uuid.UUID, list[AIRun]] = {}

    for run in runs:
        if run.ticket_id:
            runs_by_ticket.setdefault(run.ticket_id, []).append(run)
            ai_ticket_costs[run.ticket_id] = ai_ticket_costs.get(run.ticket_id, 0.0) + float(run.estimated_cost_usd or 0)

    # Why: a ticket counts as "AI-assisted" only if at least one AIRun
    # started before the first close transition — runs created after the
    # ticket was closed cannot have helped solve it.
    for ticket in tickets:
        closed_at = first_close.get(ticket.id)
        if not closed_at:
            continue
        created_at = ensure_utc(ticket.created_at)
        assert created_at is not None
        time_to_close_hours = round((closed_at - created_at).total_seconds() / 3600, 2)
        had_ai = any(
            (ensure_utc(run.started_at) or datetime.min.replace(tzinfo=timezone.utc)) <= closed_at
            for run in runs_by_ticket.get(ticket.id, [])
        )
        if had_ai:
            closed_with_ai += 1
            close_with_ai_hours.append(time_to_close_hours)
        else:
            closed_without_ai += 1
            close_without_ai_hours.append(time_to_close_hours)

    ai_ticket_count = len(ai_ticket_costs)
    return {
        "total_runs": total_runs,
        "runs_by_surface": runs_by_surface,
        "success_rate": round(success_count / total_runs, 4) if total_runs else 0.0,
        "fallback_rate": round(fallback_count / total_runs, 4) if total_runs else 0.0,
        "total_rag_queries": total_rag_queries,
        "rag_hit_rate": round(min(total_rag_hits, total_rag_queries) / total_rag_queries, 4) if total_rag_queries else 0.0,
        "positive_feedback_count": positive_feedback,
        "negative_feedback_count": negative_feedback,
        "helped_rate": round(positive_feedback / len(feedback_rows), 4) if feedback_rows else 0.0,
        "tickets_closed_with_ai": closed_with_ai,
        "tickets_closed_without_ai": closed_without_ai,
        "avg_time_to_close_with_ai_hours": round(sum(close_with_ai_hours) / len(close_with_ai_hours), 2) if close_with_ai_hours else None,
        "avg_time_to_close_without_ai_hours": round(sum(close_without_ai_hours) / len(close_without_ai_hours), 2) if close_without_ai_hours else None,
        "total_estimated_cost_usd": round(total_cost, 6),
        "avg_cost_per_run_usd": round(total_cost / total_runs, 6) if total_runs else 0.0,
        "avg_cost_per_ticket_with_ai_usd": round(total_cost / ai_ticket_count, 6) if ai_ticket_count else 0.0,
    }


async def get_ticket_stats(db: AsyncSession, ticket_id: uuid.UUID) -> dict:
    """Return AI usage metrics scoped to a single ticket.

    Raises:
        ValueError: If `ticket_id` does not exist.
    """
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise ValueError("Ticket not found")

    runs = (
        await db.execute(select(AIRun).where(AIRun.ticket_id == ticket_id).order_by(AIRun.started_at.desc()))
    ).scalars().all()
    run_ids = [run.id for run in runs]
    feedback_rows = []
    if run_ids:
        feedback_rows = (
            await db.execute(select(AIFeedback).where(AIFeedback.ai_run_id.in_(run_ids)))
        ).scalars().all()

    first_close = await _first_close_map(db)
    closed_at = first_close.get(ticket_id)
    time_to_close_hours = None
    if closed_at:
        created_at = ensure_utc(ticket.created_at)
        assert created_at is not None
        time_to_close_hours = round((closed_at - created_at).total_seconds() / 3600, 2)

    diagnosis_runs = sum(1 for run in runs if run.surface == "diagnosis")
    chat_runs = sum(1 for run in runs if run.surface == "chat")
    rag_queries = sum(run.rag_queries_count for run in runs)
    rag_hits = sum(run.rag_hits_count for run in runs)
    positive_feedback = sum(1 for fb in feedback_rows if fb.helped)
    negative_feedback = sum(1 for fb in feedback_rows if not fb.helped)
    helped = None if positive_feedback == negative_feedback == 0 else positive_feedback >= negative_feedback

    return {
        "ticket_id": ticket_id,
        "diagnosis_runs": diagnosis_runs,
        "chat_runs": chat_runs,
        "rag_queries_count": rag_queries,
        "rag_hit_rate": round(min(rag_hits, rag_queries) / rag_queries, 4) if rag_queries else 0.0,
        "last_ai_used_at": ensure_utc(runs[0].started_at) if runs else None,
        "positive_feedback_count": positive_feedback,
        "negative_feedback_count": negative_feedback,
        "helped": helped,
        "first_closed_at": closed_at,
        "time_to_close_hours": time_to_close_hours,
        "estimated_cost_usd": round(float(sum(Decimal(run.estimated_cost_usd or 0) for run in runs)), 6),
    }
