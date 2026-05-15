"""Redis Pub/Sub fan-out for WebSocket events.

Bridges the Redis channel that backend replicas use to share real-time
events with the in-process `WebSocketManager`. The publish side is
called from the notification service; the listen side runs as a single
background task started during application startup.
"""

import asyncio
import json
import logging
from app.schemas.notification import NotificationPayload

logger = logging.getLogger(__name__)

CHANNEL = "notifications"


async def publish(payload: dict) -> None:
    """Publish a WebSocket event payload to the shared Redis channel.

    When Redis is unavailable the caller (`notification_service`) is
    expected to fall back to `pg_notify`; this function only attempts the
    Redis path.
    """
    from app.services.cache_service import _redis

    if _redis is not None:
        try:
            await _redis.publish(CHANNEL, json.dumps(payload))
            return
        except Exception as exc:
            logger.warning("Redis publish failed, falling back to PG NOTIFY: %s", exc)

    _pg_notify_fn = payload.pop("_pg_notify_fn", None)
    if _pg_notify_fn is not None:
        await _pg_notify_fn(payload)


async def redis_listen_loop() -> None:
    """Subscribe to the Redis channel and dispatch messages to local sockets.

    Each message carries a `user_id`; when it equals `"*"` the event is
    broadcast to every connected socket, otherwise it is routed to the
    specific user. The loop survives transient Redis errors and exits
    cleanly on `CancelledError` (FastAPI shutdown).
    """
    from app.services.cache_service import _redis
    from app.core.websocket_manager import manager

    if _redis is None:
        logger.info("Redis not available — skipping Redis listen loop")
        return

    try:
        pubsub = _redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        logger.info("Redis pub/sub subscribed to channel '%s'", CHANNEL)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                raw_data = json.loads(message["data"])
                user_id = raw_data.pop("user_id", None)
                if not user_id:
                    continue

                from app.schemas.websocket import WSMessage
                ws_msg = WSMessage(**raw_data)
                if user_id == "*":
                    await manager.broadcast_to_all(ws_msg)
                else:
                    await manager.broadcast_to_user(str(user_id), ws_msg)
            except Exception as exc:
                logger.debug("Error processing pub/sub message: %s", exc)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("Redis listen loop error: %s", exc)
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass


def is_redis_available() -> bool:
    """Return `True` if the shared Redis client is connected."""
    from app.services.cache_service import _redis
    return _redis is not None
