from fastapi import FastAPI, WebSocket
import redis

app = FastAPI()

r = redis.Redis(host="localhost", port=6379)

@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()

    pubsub = r.pubsub()
    pubsub.subscribe("updates")

    for msg in pubsub.listen():
        if msg["type"] == "message":
            await ws.send_text(msg["data"].decode())