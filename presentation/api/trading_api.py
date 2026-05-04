from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.application.dto import serialize_signal
from app.application.trading_service import TradingService


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
def generate_signals(payload: StrategyRunRequest) -> list[dict[str, Any]]:
    signals = service.run_strategy(strategy_name=payload.strategy_name, data=payload.candles, symbol=payload.symbol, capital=payload.capital, risk_pct=payload.risk_pct, rr_ratio=payload.rr_ratio)
    return [serialize_signal(signal) for signal in signals]


@router.get("/strategies")
def list_strategies() -> list[str]:
    return service.trading_engine.strategy_engine.available()
