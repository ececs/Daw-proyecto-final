"""Enterprise-grade real-time notification distribution manager.

Coordinates the multi-channel publication of incident alerts and ticket event triggers.
Utilizes Redis Pub/Sub for horizontally scalable real-time delivery, seamlessly reverting 
back to single-instance PostgreSQL LISTEN/NOTIFY protocols for standalone environments. 
Aggregates event persistence and provides transactional delivery guarantees.
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
    """Transmits direct SQL database NOTIFY calls over isolated local notifications channels.

    Executed exclusively as the fallback transport mechanism when Redis pooling is offline.
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
    """Directs message packets toward active client transport layers via PubSub/SQL.

    Verifies the primary distributed cache state before determining active route logic.
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
    """Appends an alert entity to physical storage and triggers instant distribution alerts.

    Ensures the underlying entity generates an artificial identifier before initiating
    downstream publish actions, and dynamically calculates fresh unread statistics counters.

    Returns:
        Notification: The flushed ORM instance ready for primary transaction finalization.
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
    """Broadcasts completion telemetry alerting users that background RAG jobs concluded."""
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
    """Alerts creators and direct assignees upon the initialization of new ticket entities."""
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
    """Dispatches historical alert confirmation documenting hard object deletion cycles."""
    await _create_notification(
        db,
        user_id=actor.id,
        notification_type=NotificationType.ticket_deleted,
        ticket_id=None,
        message=f'Ticket "{ticket_title}" eliminado por {actor.name}.',
    )


async def notify_ticket_deletion_requested(
    db: AsyncSession,
    ticket: Ticket,
    requester: User,
) -> None:
    """Requests authority validation from creators concerning deletion solicitations."""
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
    """Apprises identified user profiles regarding newly bound assignment directives."""
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
    """Alerts interested stakeholders whenever updated commentary spans are submitted."""
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
    """Fires prioritized transition signals tracking importance rank migrations."""
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
    """Broadcasts status workflow progressions spanning from registration to resolution."""
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
    """Emits broadcast events to every active WebSocket connection instance.

    Targets a specialized user wild-card '*' matching universal dispatch tunnels.
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
    """Transmits immediate transient signals tracking active user interfaces states.

    Employed to synchronize transient frontend properties, such as typing cursors
    or active edit fields, maintaining live UI consistency across sessions.
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
    """Drives universal visual synchronization refreshes tracking metadata changes."""
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
    """Queries chronologically ordered historical alert arrays bound to target users."""
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
    """Updates targeted alert state markers to 'read' releasing unread quotas.

    Transmits synchronized dismissal event notices via user messaging routes.
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
    """Deletes single historical notifications bound to verifying user contexts."""
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
    """Aggregates and executes bulk read updates modifying unread flag statuses."""
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
    """Forces global dismissal operations across parallel client session tabs."""
    ws_msg = WSMessage(
        type=WSMessageType.NOTIFICATIONS_READ_ALL,
        data={"unread_count": unread_count},
    )
    await _publish_user_event(db, user_id, ws_msg)
    await db.commit()


async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Executes optimized SQL count aggregates scanning for active alert statuses."""
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
    """Retrieves prioritized historical enumerations filtering for active unread states."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [NotificationOut.model_validate(n) for n in notifications]
