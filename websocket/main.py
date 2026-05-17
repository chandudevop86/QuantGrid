import asyncio
import os

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
import redis

app = FastAPI()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL)

@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()

    pubsub = r.pubsub()
    pubsub.subscribe("updates")

    try:
        while True:
            msg = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
            if msg and msg["type"] == "message":
                await ws.send_text(msg["data"].decode())
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        pubsub.close()
