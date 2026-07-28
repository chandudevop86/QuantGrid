from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.repository.candle_repository import candle_repository
from app.cache.redis_client import get_latest_candle

router = APIRouter(
    prefix="/market",
    tags=["Market Data"],
)


@router.get("/latest")
def latest_candle(
    symbol: str,
    interval: str = "1",
    db: Session = Depends(get_db),
):
    # Redis first (fastest)
    data = get_latest_candle(symbol)

    if data:
        return data

    # Fallback to PostgreSQL
    candle = candle_repository.get_latest(
        db,
        symbol,
        interval,
    )

    if not candle:
        return {
            "symbol": symbol,
            "status": "no_data",
        }

    return {
        "symbol": candle.symbol,
        "interval": candle.interval,
        "timestamp": candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "source": candle.source,
    }


@router.get("/history")
def history(
    symbol: str,
    interval: str = "1",
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
):
    candles = candle_repository.get_history(
        db,
        symbol,
        interval,
        limit,
    )

    return [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]


@router.get("/symbols")
def symbols():
    return {
        "symbols": [
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
        ]
    }