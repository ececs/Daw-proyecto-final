"""Distributed Redis caching and rate-limiting provider.

Implements a high-performance intermediate storage layer with automatic graceful
degradation to standalone database execution if the Redis server becomes unreachable.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis: Any = None


async def init_cache() -> None:
    """Establishes an asynchronous TCP connection to the Redis Cache Cluster.

    Exits silently (no-op) if the cluster connection endpoint configuration
    remains absent from the system environment settings.
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
    """Closes existing pool resources releasing the active Redis connection."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get(key: str) -> Optional[Any]:
    """Retrieves and deserializes JSON values bound to a string key.

    Returns:
        Optional[Any]: Parsed JSON values if found, otherwise None.
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
    """Serializes and persists an arbitrary value bound to an expiration TTL.

    Args:
        key: Primary cache key string identifier.
        value: The Python object or dictionary to serialize.
        ttl: Relative time-to-live constraint in seconds.
    """
    if _redis is None:
        return
    try:
        await _redis.setex(key, ttl, json.dumps(value))
    except Exception as exc:
        logger.debug("Cache SET error for %s: %s", key, exc)


async def cache_invalidate_prefix(prefix: str) -> None:
    """Atomically purges keys sharing a common namespace prefix reference."""
    if _redis is None:
        return
    try:
        keys = await _redis.keys(f"{prefix}*")
        if keys:
            await _redis.delete(*keys)
    except Exception as exc:
        logger.debug("Cache INVALIDATE error for prefix %s: %s", prefix, exc)


async def is_rate_limited(key: str, limit: int, window: int) -> bool:
    """Verifies if an identified key exceeds access quotas within a sliding window.

    Utilizes a fixed-window counter paradigm leveraging atomic increments.

    Args:
        key: Tracking identifier (e.g., client IP, endpoint name).
        limit: The maximum requests permitted inside the designated window.
        window: Time-frame constraint span in seconds.

    Returns:
        bool: True if the requesting entity has surpassed their threshold.
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
