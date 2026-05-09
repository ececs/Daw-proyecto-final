"""
In-memory AI observability store.

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
    """Called once when the agent is built to register active model info."""
    with _lock:
        _state.provider = provider
        _state.model = model
        _state.fallback_available = fallback_available
        _state.fallback_model = fallback_model


def increment_action() -> None:
    """Increment the tool-action counter. Called on every agent tool_end event."""
    with _lock:
        _state.action_count += 1


def increment_chat() -> None:
    """Called on each POST /ai/chat request."""
    with _lock:
        _state.chat_count += 1
        _state.last_surface = "chat"


def increment_diagnosis() -> None:
    """Called when a streaming AI diagnosis is started."""
    with _lock:
        _state.diagnoses_count += 1
        _state.last_surface = "diagnosis"


def increment_rag_query(had_results: bool) -> None:
    """Called on each search_knowledge tool call."""
    with _lock:
        _state.rag_queries_count += 1
        if had_results:
            _state.rag_hits_count += 1


def record_rag(queries: int, hits: int, source: str) -> None:
    with _lock:
        _state.rag_queries_count += max(0, queries)
        _state.rag_hits_count += max(0, hits)
        _state.last_rag_source = source or "none"


def record_fallback() -> None:
    with _lock:
        _state.fallback_count += 1


def record_success(surface: str, latency_ms: Optional[int], rag_source: Optional[str] = None) -> None:
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
    """Store the most recent error message with a UTC timestamp."""
    with _lock:
        _state.error_count += 1
        _state.last_error = message[:300]
        _state.last_error_at = datetime.now(timezone.utc).isoformat()
        if surface:
            _state.last_surface = surface


def get_status() -> dict:
    """Return a snapshot of the current observability state."""
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
