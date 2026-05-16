from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

router = APIRouter(tags=["market"])


@router.get("/price")
def get_price():
    return {
        "symbol": "NIFTY",
        "price": 22450,
        "change": "+0.85%"
    }


@router.get("/signals")
def get_signals():
    return {
        "signal": "BUY",
        "confidence": 0.78
    }


@router.get("/candles/{symbol}")
def get_candles(symbol: str):
    start = datetime.now(timezone.utc) - timedelta(minutes=4)
    candles = []

    for index in range(5):
        open_price = 22440 + index * 3
        candles.append({
            "symbol": symbol.upper(),
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": open_price + 8,
            "low": open_price - 6,
            "close": open_price + 4,
            "volume": 1000 + index * 125,
        })

    return {"candles": candles}
