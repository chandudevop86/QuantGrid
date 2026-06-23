from __future__ import annotations

import asyncio
import os

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self.max_connections = max(1, int(os.getenv("QUANTGRID_MAX_WEBSOCKET_CONNECTIONS", "100")))

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

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

    async def broadcast(self, message: dict) -> None:
        disconnected: list[WebSocket] = []

        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()
