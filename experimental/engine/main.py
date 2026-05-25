from kafka import KafkaConsumer, KafkaProducer
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quantgrid-engine")

consumer = KafkaConsumer(
    "orders",
    bootstrap_servers="localhost:9092"
)

producer = KafkaProducer(
    bootstrap_servers="localhost:9092"
)

print("Engine started...")

for msg in consumer:
    try:
        order = json.loads(msg.value)
    except json.JSONDecodeError:
        logger.warning("Skipping invalid order message: %r", msg.value)
        continue

    order_id = order.get("id") if isinstance(order, dict) else None
    if not order_id:
        logger.warning("Skipping order without id: %r", order)
        continue

    print("Executing:", order)

    result = {
        "order_id": order_id,
        "status": "FILLED"
    }

    producer.send(
        "execution-reports",
        json.dumps(result).encode()
    )
