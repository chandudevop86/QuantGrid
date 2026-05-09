from kafka import KafkaConsumer
import redis

consumer = KafkaConsumer(
    "execution-reports",
    bootstrap_servers="localhost:9092"
)

r = redis.Redis(host="localhost", port=6379)

for msg in consumer:
    r.publish("updates", msg.value)
    