from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Any

from Backend.application.dto import serialize_signal
from Backend.application.signal_validation import validate_signals
from Backend.application.trading_service import TradingService
from Backend.presentation.api.roles import require_roles

router = APIRouter(tags=["Trading"])




class StrategyRunRequest(BaseModel):
    strategy_name: str
    symbol: str
    capital: float
    risk_pct: float
    rr_ratio: float = 2.0
    candles: list[dict[str, Any]]


@router.post("/signals")
def generate_signals(
    payload: StrategyRunRequest,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
):
    service = TradingService()
    signals = service.run_strategy(
        strategy_name=payload.strategy_name,
        data=payload.candles,
        symbol=payload.symbol,
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
    )
    validated_signals, _data_source = validate_signals(
        signals,
        symbol=payload.symbol,
        candles=payload.candles,
        candle_source="yahoo-finance",
    )
    return [serialize_signal(s) for s in validated_signals]


@router.get("/strategies")
def list_strategies():
    return service.trading_engine.strategy_engine.available()
