"""WebSocket gateway for low-latency real-time user interactions.

Establishes persistent duplex connections enabling live event pushes spanning 
immediate system alerts, live typing presence, and asynchronous RAG completions.
Leverages local standalone DB context managers isolating active protocol loops.
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
    """Establishes persistent socket tunnels transmitting real-time server notifications.

    Authenticates inbound query tokens, broadcasts initial historical alerts count states,
    and cycles through continuous keep-alive wait-loops ensuring connection stability.

    Args:
        websocket: Specialized inbound duplex communication protocol object.
        token: Signed JWT string mapping user identity attributes.

    Closes:
        Code 4001: Issued upon token invalidation or missing database user records.
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

        from app.schemas.websocket import WSMessage, WSMessageType
        
        unread_count = await notification_service.get_unread_count(db, user.id)
        msg = WSMessage(
            type=WSMessageType.SYSTEM_ALERT,
            data={"unread_count": unread_count},
            message="Estado inicial cargado"
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

    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_text('{"type":"ping"}')
    except WebSocketDisconnect:
        manager.disconnect(websocket, user.id)
