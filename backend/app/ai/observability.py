"""In-memory thread-safe AI observability telemetry store.

Tracks provider, active model, fallback availability, last error, and a
cumulative tool-action counter. State resets on process restart — this is
intentional: the goal is operational visibility of the current run, not
long-term analytics.

Thread-safe via a threading.Lock (uvicorn workers share one process in dev).
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class _AIState:
    """Encapsulates core operational usage metrics in a memory structure."""
    provider: str = "unknown"
    model: str = "unknown"
    fallback_available: bool = False
    fallback_model: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    # Usage counters — reset on process restart
    action_count: int = 0       # agent tool executions
    chat_count: int = 0         # /ai/chat POST requests
    diagnoses_count: int = 0    # AI copilot diagnoses streamed
    rag_queries_count: int = 0  # search_knowledge tool calls
    rag_hits_count: int = 0     # searches that returned ≥1 chunk
    fallback_count: int = 0
    success_count: int = 0
    error_count: int = 0
    last_latency_ms: Optional[int] = None
    latency_total_ms: int = 0
    latency_samples: int = 0
    avg_latency_ms: Optional[float] = None
    last_surface: Optional[str] = None
    last_rag_source: str = "none"


_state = _AIState()
_lock = threading.Lock()


def configure(
    provider: str,
    model: str,
    fallback_available: bool,
    fallback_model: Optional[str] = None,
) -> None:
    """Registers static deployment info for the active AI provider engine.

    Args:
        provider: String ID representing the primary provider.
        model: The primary LLM deployment model identifier.
        fallback_available: Flag denoting if a secondary LLM model is active.
        fallback_model: String name of the optional fallback LLM.
    """
    with _lock:
        _state.provider = provider
        _state.model = model
        _state.fallback_available = fallback_available
        _state.fallback_model = fallback_model


def increment_action() -> None:
    """Increments the cumulative counter tracking discrete agent tool executions."""
    with _lock:
        _state.action_count += 1


def increment_chat() -> None:
    """Tracks the arrival of an incoming chat endpoint message execution."""
    with _lock:
        _state.chat_count += 1
        _state.last_surface = "chat"


def increment_diagnosis() -> None:
    """Registers the bootstrap initiation of a streaming ticket diagnostic run."""
    with _lock:
        _state.diagnoses_count += 1
        _state.last_surface = "diagnosis"


def increment_rag_query(had_results: bool) -> None:
    """Captures executing knowledge base queries assessing retrieval hit yields.

    Args:
        had_results: Denotes whether the executed query returned documents.
    """
    with _lock:
        _state.rag_queries_count += 1
        if had_results:
            _state.rag_hits_count += 1


def record_rag(queries: int, hits: int, source: str) -> None:
    """Aggregates batch RAG execution counters reflecting multiple retrieval passes.

    Args:
        queries: The number of sequential search queries triggered.
        hits: Combined count of queries successfully resolving context docs.
        source: String describing provenance (e.g., URL list, attachment key).
    """
    with _lock:
        _state.rag_queries_count += max(0, queries)
        _state.rag_hits_count += max(0, hits)
        _state.last_rag_source = source or "none"


def record_fallback() -> None:
    """Records an instance of the agent recovering through secondary fallback invocation."""
    with _lock:
        _state.fallback_count += 1


def record_success(surface: str, latency_ms: Optional[int], rag_source: Optional[str] = None) -> None:
    """Logs a completed successfully agent execution calculating rolling latencies.

    Args:
        surface: Identifier mapping endpoint origin ('chat', 'diagnosis').
        latency_ms: Total duration in milliseconds to process requests.
        rag_source: String origin identification for referenced knowledge.
    """
    with _lock:
        _state.success_count += 1
        _state.last_surface = surface
        if rag_source:
            _state.last_rag_source = rag_source
        if latency_ms is not None:
            _state.last_latency_ms = latency_ms
            _state.latency_total_ms += latency_ms
            _state.latency_samples += 1
            _state.avg_latency_ms = round(_state.latency_total_ms / _state.latency_samples, 2)


def record_error(message: str, surface: Optional[str] = None) -> None:
    """Stores failure logs attaching sanitized stack trace snippets and timestamps.

    Args:
        message: Raw exception or error message to capture.
        surface: Origin triggering context string identity.
    """
    with _lock:
        _state.error_count += 1
        _state.last_error = message[:300]
        _state.last_error_at = datetime.now(timezone.utc).isoformat()
        if surface:
            _state.last_surface = surface


def get_status() -> dict:
    """Generates a point-in-time dictionary serialization of all live telemetry.

    Returns:
        dict: Operational health map describing provider health and active usage.
    """
    with _lock:
        return {
            "provider": _state.provider,
            "model": _state.model,
            "fallback_available": _state.fallback_available,
            "fallback_model": _state.fallback_model,
            "last_error": _state.last_error,
            "last_error_at": _state.last_error_at,
            "action_count": _state.action_count,
            "chat_count": _state.chat_count,
            "diagnoses_count": _state.diagnoses_count,
            "rag_queries_count": _state.rag_queries_count,
            "rag_hits_count": _state.rag_hits_count,
            "fallback_count": _state.fallback_count,
            "success_count": _state.success_count,
            "error_count": _state.error_count,
            "last_latency_ms": _state.last_latency_ms,
            "avg_latency_ms": _state.avg_latency_ms,
            "last_surface": _state.last_surface,
            "last_rag_source": _state.last_rag_source,
        }
