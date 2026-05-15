"""WebSocket connection manager.

This module manages the lifecycle of all active WebSocket connections.
It is the bridge between server-side events (PostgreSQL NOTIFY messages)
and connected browser clients.

Architecture:
  - Each authenticated user can have multiple browser tabs/windows open,
    each with its own WebSocket connection.
  - Connections are stored in a dict keyed by user_id (UUID).
  - The value is a list of WebSocket objects (one per open tab).

When a notification must be delivered to user X:
  1. PostgreSQL triggers a NOTIFY with the user's UUID as the channel.
  2. The asyncpg listener (in main.py lifespan) calls manager.broadcast_to_user().
  3. The manager sends the JSON payload to all active connections for that user.
  4. If a connection is broken (client disconnected), it is removed gracefully.
"""

import json
import uuid
from fastapi import WebSocket
from app.schemas.websocket import WSMessage


class WebSocketManager:
    """In-process registry of active WebSocket connections.

    Maps `user_id` (string) to a list of open sockets so the same user
    can have multiple tabs receiving the same events. The registry is
    not shared across replicas — cross-process fan-out is handled by
    `pubsub_service` on top of Redis Pub/Sub.
    """

    def __init__(self) -> None:
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: uuid.UUID) -> None:
        """Accept the socket and add it to the user's connection list."""
        await websocket.accept()
        key = str(user_id)
        if key not in self.connections:
            self.connections[key] = []
        self.connections[key].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID) -> None:
        """Remove a closed socket and prune the entry when it becomes empty."""
        key = str(user_id)
        if key in self.connections:
            self.connections[key] = [
                ws for ws in self.connections[key] if ws is not websocket
            ]
            if not self.connections[key]:
                del self.connections[key]

    async def broadcast_to_all(self, data: dict | WSMessage) -> None:
        """Send `data` to every connected user (used by global events)."""
        for user_id in list(self.connections.keys()):
            await self.broadcast_to_user(user_id, data)

    async def broadcast_to_user(self, user_id: str, data: dict | WSMessage) -> None:
        """Send `data` to all sockets of `user_id`, dropping broken ones.

        Accepts both `WSMessage` instances (serialised via Pydantic) and
        raw dicts. Sockets that raise during `send_text` are considered
        dead and removed from the registry so we do not retry forever.
        """
        if user_id not in self.connections:
            return 

        if isinstance(data, WSMessage):
            message = data.model_dump_json()
        elif isinstance(data, dict):
            # Fallback for raw dicts, though WSMessage is preferred
            message = json.dumps(data)
        else:
            message = str(data)
        dead_connections: list[WebSocket] = []

        for websocket in self.connections[user_id]:
            try:
                await websocket.send_text(message)
            except Exception:
                # Connection is broken (client disconnected without clean close)
                dead_connections.append(websocket)

        # Remove broken connections
        for ws in dead_connections:
            self.connections[user_id] = [c for c in self.connections[user_id] if c is not ws]


# Singleton instance — imported in main.py and ws.py
manager = WebSocketManager()
