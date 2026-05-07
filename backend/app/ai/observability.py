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
    action_count: int = 0


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
        }
