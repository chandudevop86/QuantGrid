from __future__ import annotations

import asyncio
import os

from fastapi import WebSocket

from Backend.application.monitoring import observe_websocket_disconnect
from Backend.application.redis_service import redis_service


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self.max_connections = max(1, int(os.getenv("QUANTGRID_MAX_WEBSOCKET_CONNECTIONS", "100")))
        self.channel = os.getenv("QUANTGRID_WS_REDIS_CHANNEL", "quantgrid:websocket:broadcasts")
        self._subscriber_task: asyncio.Task | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        if redis_service.status().get("healthy") and self._subscriber_task is None:
            self._subscriber_task = loop.create_task(redis_service.subscribe_json(self.channel, self._broadcast_local))

    async def connect(self, websocket: WebSocket, *, subprotocol: str | None = None) -> bool:
        if len(self.active_connections) >= self.max_connections:
            await websocket.close(code=1013, reason="WebSocket capacity reached")
            return False
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            observe_websocket_disconnect("client_disconnect")

    async def broadcast(self, message: dict) -> None:
        published = await redis_service.publish_json(self.channel, message)
        if published:
            return
        await self._broadcast_local(message)

    async def _broadcast_local(self, message: dict) -> None:
        disconnected: list[WebSocket] = []

        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()
