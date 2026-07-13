from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import WebSocket

from Backend.application.monitoring import observe_websocket_disconnect
from Backend.application.redis_service import redis_service

logger = logging.getLogger("quantgrid.websocket")


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self.max_connections = _positive_int_env("QUANTGRID_MAX_WEBSOCKET_CONNECTIONS", 100)
        self.send_timeout_seconds = _positive_float_env("QUANTGRID_WEBSOCKET_SEND_TIMEOUT_SECONDS", 2.0)
        self.channel = os.getenv("QUANTGRID_WS_REDIS_CHANNEL", "quantgrid:websocket:broadcasts")
        self.instance_id = uuid.uuid4().hex
        self._subscriber_task: asyncio.Task | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        if self._subscriber_task is None or self._subscriber_task.done():
            self._subscriber_task = loop.create_task(redis_service.subscribe_json(self.channel, self._handle_redis_message))

    async def shutdown(self) -> None:
        task = self._subscriber_task
        self._subscriber_task = None
        self.loop = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def connect(self, websocket: WebSocket, *, subprotocol: str | None = None) -> bool:
        if len(self.active_connections) >= self.max_connections:
            await websocket.close(code=1013, reason="WebSocket capacity reached")
            logger.warning("websocket_rejected_capacity", extra={"active_connections": len(self.active_connections)})
            return False
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.append(websocket)
        logger.info("websocket_connected", extra={"active_connections": len(self.active_connections), "subprotocol": subprotocol})
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            observe_websocket_disconnect("client_disconnect")
            logger.info("websocket_disconnected", extra={"active_connections": len(self.active_connections)})

    async def broadcast(self, message: dict) -> None:
        await asyncio.gather(
            self._broadcast_local(message),
            redis_service.publish_json(self.channel, {**message, "_quantgrid_origin": self.instance_id}),
        )

    async def _handle_redis_message(self, message: dict) -> None:
        if message.get("_quantgrid_origin") == self.instance_id:
            return
        payload = {key: value for key, value in message.items() if key != "_quantgrid_origin"}
        await self._broadcast_local(payload)

    async def _broadcast_local(self, message: dict) -> None:
        async def send(connection: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(connection.send_json(message), timeout=self.send_timeout_seconds)
                return None
            except Exception as exc:
                logger.warning("websocket_broadcast_failed", extra={"error_type": exc.__class__.__name__})
                return connection

        results = await asyncio.gather(*(send(connection) for connection in list(self.active_connections)))
        for connection in results:
            if connection is not None:
                self.disconnect(connection)


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        logger.warning("invalid_websocket_integer_config", extra={"setting": name, "fallback": default})
        return default


def _positive_float_env(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        logger.warning("invalid_websocket_float_config", extra={"setting": name, "fallback": default})
        return default


manager = ConnectionManager()
