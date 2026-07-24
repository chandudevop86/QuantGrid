from datetime import datetime, timedelta
import random


def generate_test_candles(count=100, start_price=25000):
    candles = []

    ts = datetime(2026, 7, 24, 9, 15)
    price = start_price

    for _ in range(count):
        open_price = price
        high = open_price + random.uniform(10, 35)
        low = open_price - random.uniform(10, 35)
        close = random.uniform(low, high)
        volume = random.randint(1000, 5000)

        candles.append({
            "timestamp": ts,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume,
        })

        ts += timedelta(minutes=1)
        price = close + random.uniform(-8, 12)

    return candles