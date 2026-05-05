from __future__ import annotations
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from application.dto import serialize_signal
from application.trading_service import TradingService

router = APIRouter(prefix="/trading", tags=["trading"])
service = TradingService()


class StrategyRunRequest(BaseModel):
    strategy_name: str = Field(examples=["amd", "breakout", "mean_reversion"])
    symbol: str
    capital: float
    risk_pct: float
    rr_ratio: float = 2.0
    candles: list[dict[str, Any]]


@router.post("/signals")
def generate_signals(payload: StrategyRunRequest):
    signals = service.run_strategy(
        strategy_name=payload.strategy_name,
        data=payload.candles,
        symbol=payload.symbol,
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
    )
    return [serialize_signal(signal) for signal in signals]


@router.get("/strategies")
def list_strategies():
    return service.trading_engine.strategy_engine.available()

from fastapi import APIRouter

router = APIRouter()

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