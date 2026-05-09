from fastapi import FastAPI
from kafka import KafkaProducer
import json, uuid

app = FastAPI()

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode()
)

@app.post("/order")
def place_order(order: dict):
    order["id"] = str(uuid.uuid4())

    producer.send("orders", order)

    return {
        "status": "sent",
        "order_id": order["id"]
    }