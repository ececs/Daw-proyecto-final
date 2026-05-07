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


def increment_diagnosis() -> None:
    """Called when a streaming AI diagnosis is started."""
    with _lock:
        _state.diagnoses_count += 1


def increment_rag_query(had_results: bool) -> None:
    """Called on each search_knowledge tool call."""
    with _lock:
        _state.rag_queries_count += 1
        if had_results:
            _state.rag_hits_count += 1


def record_error(message: str) -> None:
    """Store the most recent error message with a UTC timestamp."""
    with _lock:
        _state.last_error = message[:300]
        _state.last_error_at = datetime.now(timezone.utc).isoformat()


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
        }
