"""Real-time notification service.

Owns the multi-channel delivery of in-app notifications and live updates:

- Persists `Notification` rows so the bell icon survives reconnects.
- Pushes events over **Redis Pub/Sub** when available so multiple backend
  replicas can broadcast to all connected sockets.
- Falls back to PostgreSQL `LISTEN/NOTIFY` for single-process / local
  development deployments where Redis is not configured.

Most public functions follow the same shape: persist the notification,
compute the user's new unread count, and forward a `WSMessage` to the
right transport.
"""

import json
import logging
from typing import List, Optional, Any, Dict
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func

from app.models.notification import Notification, NotificationType
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.notification import NotificationOut
from app.services import pubsub_service
from app.schemas.websocket import WSMessage, WSMessageType

logger = logging.getLogger(__name__)


async def _pg_notify(db: AsyncSession, user_id: str, payload: dict) -> None:
    """Emit a PostgreSQL `NOTIFY` on the `notifications` channel.

    Used only as a fallback when Redis is not available; the WebSocket
    process is expected to be `LISTEN`-ing on the same channel.
    """
    payload["user_id"] = user_id
    payload_str = json.dumps(payload, default=str)
    await db.execute(
        text("SELECT pg_notify('notifications', :payload)"),
        {"payload": payload_str},
    )


async def _publish_user_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    ws_msg: WSMessage,
) -> None:
    """Deliver a per-user `WSMessage` through Redis or PG NOTIFY.

    Redis is preferred because it works across multiple backend replicas;
    `pg_notify` is the single-instance fallback.
    """
    event = ws_msg.model_dump(mode="json")
    event["user_id"] = str(user_id)

    if pubsub_service.is_redis_available():
        await pubsub_service.publish(event)
        logger.debug("Broadcasted %s to user %s via Redis", ws_msg.type, user_id)
    else:
        await _pg_notify(db, str(user_id), event)
        logger.debug("Broadcasted %s to user %s via PG Notify", ws_msg.type, user_id)


async def _create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    notification_type: NotificationType,
    ticket_id: uuid.UUID | None,
    message: str,
) -> Notification:
    """Persist a `Notification` row and push it to the user in real time.

    The row is flushed (not committed) so the caller decides the
    transaction boundary; the WebSocket push happens *after* the flush so
    the payload contains the generated id and the up-to-date unread count.

    Returns:
        Notification: The flushed (not yet committed) ORM instance.
    """
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        ticket_id=ticket_id,
        message=message,
    )
    db.add(notification)
    await db.flush()

    unread_count = await get_unread_count(db, user_id)

    # Why: deferred import keeps the notification module importable from
    # places that only need the persistence side, without dragging in the
    # WebSocket schemas at module load time.
    from app.schemas.websocket import WSMessage, WSMessageType

    ws_msg = WSMessage(
        type=WSMessageType.NOTIFICATION,
        ticket_id=ticket_id,
        data={
            "id": str(notification.id),
            "user_id": str(user_id),
            "type": notification_type.value,
            "ticket_id": str(ticket_id) if ticket_id else None,
            "message": message,
            "read": notification.read,
            "created_at": notification.created_at.isoformat(),
            "unread_count": unread_count,
        }
    )

    logger.info(f"🔔 Notification created: type={notification_type.value}, user={user_id}, msg={message[:30]}...")
    await _publish_user_event(db, user_id, ws_msg)

    return notification


async def notify_rag_indexed(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    author_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
    message: str,
) -> None:
    """Notify the ticket's author (and assignee, if any) that RAG indexing finished."""
    users_to_notify = {author_id}
    if assignee_id:
        users_to_notify.add(assignee_id)
    for user_id in users_to_notify:
        await _create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.rag_indexed,
            ticket_id=ticket_id,
            message=message,
        )
    await db.commit()


async def notify_ticket_created(
    db: AsyncSession,
    ticket: Ticket,
    actor: User,
) -> None:
    """Notify the author and assignee that a new ticket was created."""
    users_to_notify = {ticket.author_id}
    if ticket.assignee_id:
        users_to_notify.add(ticket.assignee_id)

    for user_id in users_to_notify:
        await _create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.status_changed,
            ticket_id=ticket.id,
            message=f'New ticket created: "{ticket.title}" by {actor.name}',
        )


async def notify_ticket_deleted(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    ticket_title: str,
    actor: User,
) -> None:
    """Send a self-notification to the actor confirming the ticket was deleted."""
    await _create_notification(
        db,
        user_id=actor.id,
        notification_type=NotificationType.ticket_deleted,
        ticket_id=None,
        message=f'Ticket "{ticket_title}" was deleted by {actor.name}.',
    )


async def notify_ticket_deletion_requested(
    db: AsyncSession,
    ticket: Ticket,
    requester: User,
) -> None:
    """Notify the ticket author that another user is requesting its deletion.

    Silently no-ops if the requester is the author themselves (the API
    layer already prevents this, but the guard keeps the function safe to
    call from other entry points).
    """
    if ticket.author_id == requester.id:
        return

    await _create_notification(
        db,
        user_id=ticket.author_id,
        notification_type=NotificationType.deletion_requested,
        ticket_id=ticket.id,
        message=f'{requester.name} requested deletion of "{ticket.title}"',
    )


async def notify_ticket_assigned(
    db: AsyncSession,
    ticket: Ticket,
    assignee: User,
    actor: User,
) -> None:
    """Notify a user that a ticket has been assigned to them."""
    await _create_notification(
        db,
        user_id=assignee.id,
        notification_type=NotificationType.assigned,
        ticket_id=ticket.id,
        message=f'{actor.name} assigned ticket "{ticket.title}" to you',
    )


async def notify_comment_added(
    db: AsyncSession,
    ticket: Ticket,
    commenter: User,
) -> None:
    """Notify the author and assignee that a new comment was posted."""
    users_to_notify: set[uuid.UUID] = set()

    users_to_notify.add(ticket.author_id)

    if ticket.assignee_id:
        users_to_notify.add(ticket.assignee_id)

    for user_id in users_to_notify:
        await _create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.commented,
            ticket_id=ticket.id,
            message=f'{commenter.name} commented on "{ticket.title}"',
        )


async def notify_priority_changed(
    db: AsyncSession,
    ticket: Ticket,
    actor: User,
    new_priority: str,
) -> None:
    """Notify the author and assignee that the ticket priority changed."""
    priority_str = new_priority.value if hasattr(new_priority, "value") else new_priority
    priority_label = priority_str.replace("_", " ").title()
    message = f'{actor.name} changed priority of "{ticket.title}" to {priority_label}'

    users_to_notify: set[uuid.UUID] = set()
    users_to_notify.add(ticket.author_id)
    if ticket.assignee_id:
        users_to_notify.add(ticket.assignee_id)

    for user_id in users_to_notify:
        await _create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.ticket_updated,
            ticket_id=ticket.id,
            message=message,
        )


async def notify_status_changed(
    db: AsyncSession,
    ticket: Ticket,
    actor: User,
    new_status: str,
) -> None:
    """Notify the author and assignee that the ticket status changed."""
    status_str = new_status.value if hasattr(new_status, "value") else new_status
    status_label = status_str.replace("_", " ").title()
    message = f'{actor.name} changed "{ticket.title}" to {status_label}'

    users_to_notify: set[uuid.UUID] = set()

    users_to_notify.add(ticket.author_id)

    if ticket.assignee_id:
        users_to_notify.add(ticket.assignee_id)

    for user_id in users_to_notify:
        await _create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.status_changed,
            ticket_id=ticket.id,
            message=message,
        )


async def broadcast_global_event(
    type: WSMessageType,
    data: Optional[Dict[str, Any]] = None,
    db: Optional[AsyncSession] = None
) -> None:
    """Broadcast an event to **every** connected WebSocket client.

    The `user_id` field is set to the wildcard `"*"` so the consumer side
    knows to fan out to every active connection regardless of identity.
    Used for non-personalised events such as `TICKET_CREATED` /
    `TICKET_DELETED`.
    """
    from app.schemas.websocket import WSMessage
    from app.services import pubsub_service

    ws_msg = WSMessage(type=type, data=data)
    logger.info("Global broadcast: type=%s", type.value)
    event = ws_msg.model_dump(mode="json")
    event["user_id"] = "*"

    if pubsub_service.is_redis_available():
        await pubsub_service.publish(event)
    elif db is not None:
        await _pg_notify(db, "*", event)
        await db.commit()
    else:
        logger.warning("Global broadcast skipped: no Redis and no DB session provided.")


async def broadcast_live_update(
    user_id: uuid.UUID,
    ticket_id: uuid.UUID,
    type: WSMessageType = WSMessageType.TICKET_UPDATED,
    message: Optional[str] = None,
    db: Optional[AsyncSession] = None
) -> None:
    """Push an ephemeral, non-persisted update to a single user.

    Used to synchronise transient UI state across tabs (e.g. "user X is
    typing", or "user X opened ticket Y") without polluting the
    persistent notification feed.
    """
    from app.schemas.websocket import WSMessage

    ws_msg = WSMessage(
        type=type,
        ticket_id=ticket_id,
        message=message
    )

    event = ws_msg.model_dump(mode="json")
    event["user_id"] = str(user_id)

    logger.info(f"🔄 Live update broadcast: type={type.value}, user={user_id}, ticket={ticket_id}")

    from app.services import pubsub_service
    if pubsub_service.is_redis_available():
        await pubsub_service.publish(event)
    elif db is not None:
        await _pg_notify(db, str(user_id), event)
    else:
        logger.warning(f"Live update skipped for user {user_id}: No Redis and no DB session provided for PG Notify.")


async def notify_ticket_updated(
    db: AsyncSession,
    ticket: Ticket,
    actor: User,
) -> None:
    """Broadcast a `TICKET_UPDATED` event so all clients refresh their view."""
    await broadcast_global_event(
        type=WSMessageType.TICKET_UPDATED,
        data={
            "id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "title": ticket.title,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
        },
        db=db
    )


async def list_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50
) -> list[NotificationOut]:
    """Return the most recent notifications for `user_id` (newest first)."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [NotificationOut.model_validate(n) for n in notifications]


async def mark_read(
    db: AsyncSession,
    notification_id: uuid.UUID,
    user_id: uuid.UUID
) -> bool:
    """Mark a notification as read and push the new unread count.

    Returns:
        bool: `True` if the row belonged to `user_id` and was updated;
        `False` if no such row exists.
    """
    from sqlalchemy import update
    result = await db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
        .values(read=True)
    )
    await db.commit()
    if result.rowcount == 0:
        return False

    unread_count = await get_unread_count(db, user_id)
    ws_msg = WSMessage(
        type=WSMessageType.NOTIFICATION_READ,
        data={"id": str(notification_id), "unread_count": unread_count},
    )
    await _publish_user_event(db, user_id, ws_msg)
    await db.commit()
    return True


async def delete_notification(
    db: AsyncSession,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Delete a notification belonging to `user_id` and push the new unread count.

    Returns:
        bool: `True` if a row was deleted; `False` if it did not exist or
        did not belong to the user.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        return False

    await db.delete(notification)
    await db.commit()

    unread_count = await get_unread_count(db, user_id)
    ws_msg = WSMessage(
        type=WSMessageType.NOTIFICATION_DELETED,
        data={
            "id": str(notification_id),
            "unread_count": unread_count,
        },
    )
    await _publish_user_event(db, user_id, ws_msg)
    await db.commit()
    return True


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Mark every unread notification of `user_id` as read in a single statement.

    Returns:
        int: Number of rows updated.
    """
    from sqlalchemy import update
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)
        .values(read=True)
    )
    await db.commit()
    return result.rowcount


async def broadcast_notifications_read_all(
    db: AsyncSession,
    user_id: uuid.UUID,
    unread_count: int = 0,
) -> None:
    """Push a `NOTIFICATIONS_READ_ALL` event so every open tab zeroes its badge."""
    ws_msg = WSMessage(
        type=WSMessageType.NOTIFICATIONS_READ_ALL,
        data={"unread_count": unread_count},
    )
    await _publish_user_event(db, user_id, ws_msg)
    await db.commit()


async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Return the number of unread notifications for `user_id`."""
    result = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id, Notification.read == False)
    )
    return result.scalar() or 0


async def list_unread_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50
) -> list[NotificationOut]:
    """Return the most recent **unread** notifications of `user_id`."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [NotificationOut.model_validate(n) for n in notifications]
