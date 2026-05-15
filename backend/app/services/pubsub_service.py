"""Real-time horizontal Pub/Sub distribution layer.

Multiplexes distributed real-time WebSocket notifications across horizontally
scaled API instances. Implements primary delivery via Redis channels,
gracefully reverting back to single-instance Postgres LISTEN/NOTIFY protocols
when operating in isolated staging/development topologies.
"""

import asyncio
import json
import logging
from app.schemas.notification import NotificationPayload

logger = logging.getLogger(__name__)

CHANNEL = "notifications"


async def publish(payload: dict) -> None:
    """Publishes dynamic JSON envelopes to the designated distribution network.

    Prioritizes distributed cluster publishing; seamlessly routes to Postgres
    listener functions if standalone fallbacks are active.

    Args:
        payload: Content dictionary mapping properties of a valid NotificationPayload.
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
    """Background asynchronous daemon subscribing to real-time network events.

    Listens to global Redis notifications streams, extracting contextual
    user identifiers before dispatching structured messages down individual
    client WebSocket manager tunnels.
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
    """Verifies runtime Redis client availability to determine active transport layers."""
    from app.services.cache_service import _redis
    return _redis is not None
