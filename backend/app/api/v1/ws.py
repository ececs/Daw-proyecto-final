"""WebSocket gateway.

Single duplex endpoint used by the frontend to receive real-time events:
notifications, ticket updates and presence pings. Authentication is
performed via a JWT passed as a query parameter (WebSocket clients cannot
set custom headers from the browser).
"""

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.core.security import decode_access_token
from app.core.websocket_manager import manager
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.services import notification_service

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """Authenticate the JWT, send the initial state and keep the socket alive.

    Flow:

    1. Decode the JWT from the query string; close with code **4001** on
       failure or unknown user.
    2. Register the socket in the `WebSocketManager` so other parts of the
       backend can push events to this user.
    3. Send the initial unread-count and any pending notifications so the
       frontend can hydrate the bell icon immediately.
    4. Enter a `receive_text` loop with a 30-second timeout that doubles as
       a server-side ping to detect dead connections.

    Args:
        websocket: The accepted WebSocket connection.
        token: Signed JWT carrying the user id.

    Closes:
        4001: Invalid or missing token, or no matching user.
    """
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4001)
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            await websocket.close(code=4001)
            return

        await manager.connect(websocket, user.id)

        # Why: deferred import keeps the websocket module decoupled from
        # the schemas package at startup time.
        from app.schemas.websocket import WSMessage, WSMessageType

        unread_count = await notification_service.get_unread_count(db, user.id)
        msg = WSMessage(
            type=WSMessageType.SYSTEM_ALERT,
            data={"unread_count": unread_count},
            message="Initial state loaded"
        )
        await websocket.send_text(msg.model_dump_json())

        notifications = await notification_service.list_unread_notifications(db, user.id)
        for notif in notifications:
            notif_msg = WSMessage(
                type=WSMessageType.NOTIFICATION,
                ticket_id=notif.ticket_id,
                data=notif.model_dump(mode="json")
            )
            await websocket.send_text(notif_msg.model_dump_json())

    # Why: a blocking `receive_text` keeps the connection open; the timeout
    # turns into an application-level ping that lets us detect a half-open
    # TCP socket and exit the loop cleanly.
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_text('{"type":"ping"}')
    except WebSocketDisconnect:
        manager.disconnect(websocket, user.id)
