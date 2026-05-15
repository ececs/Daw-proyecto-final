"""Redis cache and rate-limit helpers.

Thin wrapper around a single shared `redis.asyncio` client. Every public
function is a safe no-op when Redis is not configured or temporarily
unreachable, so the rest of the backend can rely on caching as an
optimisation rather than a hard dependency.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis: Any = None


async def init_cache() -> None:
    """Connect to Redis using `settings.REDIS_URL`.

    Called from the FastAPI startup event. Failure is logged at WARN and
    leaves `_redis = None`, which makes every subsequent helper a no-op —
    the application keeps working without caching.
    """
    global _redis
    from app.core.config import settings

    if not settings.REDIS_URL:
        logger.info("Redis cache disabled (REDIS_URL not set)")
        return

    try:
        import redis.asyncio as aioredis

        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
        )
        await _redis.ping()
        logger.info("Redis cache connected: %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable — cache disabled: %s", exc)
        _redis = None


async def close_cache() -> None:
    """Close the shared Redis client. Called on FastAPI shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get(key: str) -> Optional[Any]:
    """Fetch and JSON-decode the value stored under `key`.

    Returns:
        The decoded value, or `None` on a miss / error.
    """
    if _redis is None:
        return None
    try:
        raw = await _redis.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.debug("Cache GET error for %s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    """Store `value` under `key` with a TTL of `ttl` seconds.

    Silently swallows errors — cache failures must never break the
    request that triggered them.
    """
    if _redis is None:
        return
    try:
        await _redis.setex(key, ttl, json.dumps(value))
    except Exception as exc:
        logger.debug("Cache SET error for %s: %s", key, exc)


async def cache_invalidate_prefix(prefix: str) -> None:
    """Delete every key that starts with `prefix` in a single round trip.

    Used after a mutation to invalidate every cached page of a list
    endpoint without having to track each individual cache key.
    """
    if _redis is None:
        return
    try:
        keys = await _redis.keys(f"{prefix}*")
        if keys:
            await _redis.delete(*keys)
    except Exception as exc:
        logger.debug("Cache INVALIDATE error for prefix %s: %s", prefix, exc)


async def is_rate_limited(key: str, limit: int, window: int) -> bool:
    """Return `True` if `key` has exceeded `limit` hits within `window` seconds.

    Uses the classic fixed-window counter pattern (atomic `INCR` + first-
    hit `EXPIRE`). Fixed-window has a known burst flaw at boundary
    moments but is good enough for protecting the demo login endpoint
    from naive brute-force.

    Args:
        key: Bucket identifier (typically `"<feature>:<client_ip>"`).
        limit: Maximum hits allowed within the window.
        window: Window length in seconds.
    """
    if _redis is None:
        return False
    try:
        rl_key = f"rl:{key}"
        current = await _redis.incr(rl_key)
        if current == 1:
            await _redis.expire(rl_key, window)
        return current > limit
    except Exception as exc:
        logger.debug("Rate limit error for %s: %s", rl_key, exc)
        return False
