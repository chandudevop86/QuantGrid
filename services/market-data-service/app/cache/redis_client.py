import json
import redis

from app.config import settings


redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=1,
    decode_responses=True
)


def set_latest_candle(
    symbol: str,
    candle: dict
):

    key = f"market:{symbol}:latest"

    redis_client.set(
        key,
        json.dumps(candle),
        ex=3600
    )



def get_latest_candle(
    symbol: str
):

    key = f"market:{symbol}:latest"

    data = redis_client.get(key)

    if not data:
        return None

    return json.loads(data)