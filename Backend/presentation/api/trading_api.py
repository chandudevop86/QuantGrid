from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any

from Backend.application.dto import serialize_signal
from Backend.application.trading_service import TradingService

router = APIRouter(tags=["Trading"])
service = TradingService()




class StrategyRunRequest(BaseModel):
    strategy_name: str
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
    return [serialize_signal(s) for s in signals]


@router.get("/strategies")
def list_strategies():
    return service.trading_engine.strategy_engine.available()