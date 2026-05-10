from kafka import KafkaConsumer, KafkaProducer
import json

consumer = KafkaConsumer(
    "orders",
    bootstrap_servers="localhost:9092"
)

producer = KafkaProducer(
    bootstrap_servers="localhost:9092"
)

print("Engine started...")

for msg in consumer:
    order = json.loads(msg.value)

    print("Executing:", order)

    result = {
        "order_id": order["id"],
        "status": "FILLED"
    }

    producer.send(
        "execution-reports",
        json.dumps(result).encode()
    )