import asyncio
import json
import logging
import os

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
import redis

app = FastAPI()

logger = logging.getLogger(__name__)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self.upstream_available = False

    async def connect(self, websocket: WebSocket) -> bool:
        await websocket.accept()
        if not self.upstream_available:
            await websocket.close(code=1013)
            return False

        async with self._lock:
            self.active_connections.append(websocket)
        return True

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def set_upstream_available(self, available: bool) -> None:
        self.upstream_available = available
        if not available:
            await self.close_all()

    async def close_all(self) -> None:
        async with self._lock:
            connections = list(self.active_connections)
            self.active_connections.clear()

        for connection in connections:
            try:
                await connection.close(code=1013)
            except Exception:
                pass

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            connections = list(self.active_connections)

        disconnected: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            await self.disconnect(connection)


manager = ConnectionManager()


@app.on_event("startup")
async def start_redis_listener() -> None:
    asyncio.create_task(redis_broadcast_loop())


async def redis_broadcast_loop() -> None:
    while True:
        client = redis.Redis.from_url(REDIS_URL)
        pubsub = client.pubsub()

        try:
            await asyncio.to_thread(pubsub.subscribe, "updates")
            await manager.set_upstream_available(True)

            while True:
                msg = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
                if msg and msg["type"] == "message":
                    raw_data = msg["data"].decode()
                    try:
                        payload = json.loads(raw_data)
                    except json.JSONDecodeError:
                        payload = {"message": raw_data}
                    await manager.broadcast(payload)
                await asyncio.sleep(0.05)
        except Exception:
            logger.exception("Redis websocket broadcast loop unavailable; closing websocket clients")
            await manager.set_upstream_available(False)
            await asyncio.sleep(3)
        finally:
            pubsub.close()

@app.websocket("/ws")
async def ws(ws: WebSocket):
    connected = await manager.connect(ws)
    if not connected:
        return

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
