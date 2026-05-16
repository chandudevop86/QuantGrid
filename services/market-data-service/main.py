from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import Random

from fastapi import FastAPI

app = FastAPI(title="QuantGrid Market Data Service")
random = Random(42)


@app.get("/health")
def health():
    return {"status": "ok", "service": "market-data"}


@app.get("/price/{symbol}")
def price(symbol: str):
    base = 22450 if symbol.upper() == "NIFTY" else 100
    move = round(random.uniform(-1.5, 1.5), 2)
    return {
        "symbol": symbol.upper(),
        "price": round(base + move, 2),
        "change": move,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/candles/{symbol}")
def candles(symbol: str, limit: int = 20):
    limit = max(1, min(limit, 200))
    start = datetime.now(timezone.utc) - timedelta(minutes=limit - 1)
    rows = []

    for index in range(limit):
        open_price = 22440 + index * 2
        rows.append({
            "symbol": symbol.upper(),
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": open_price + 8,
            "low": open_price - 6,
            "close": open_price + 3,
            "volume": 1000 + index * 75,
        })

    return {"candles": rows}
