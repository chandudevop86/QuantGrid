from __future__ import annotations

import uuid

from fastapi import FastAPI

from db import list_orders, save_order
from kafka_client import publisher

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok", "service": "trading"}


@app.post("/order")
def place_order(order: dict):
    order["id"] = str(uuid.uuid4())
    save_order(order["id"], order)
    published = publisher.publish("orders", order)

    return {
        "status": "sent" if published else "queued",
        "order_id": order["id"],
    }


@app.get("/orders")
def orders():
    return {"orders": list_orders()}
