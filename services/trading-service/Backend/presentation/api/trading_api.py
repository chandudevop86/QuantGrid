from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Any

from Backend.application.dto import serialize_signal
from Backend.application.signal_validation import diagnose_signal_run, validate_signals
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
    htf_candles: list[dict[str, Any]] | None = None
    mtf_candles: list[dict[str, Any]] | None = None
    daily_candles: list[dict[str, Any]] | None = None
    include_diagnostics: bool = False


@router.post("/signals")
def generate_signals(
    payload: StrategyRunRequest,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
):
    service = TradingService()
    params = {
        key: value
        for key, value in {
            "htf_candles": payload.htf_candles,
            "mtf_candles": payload.mtf_candles,
            "daily_candles": payload.daily_candles,
        }.items()
        if value is not None
    }
    signals = service.run_strategy(
        strategy_name=payload.strategy_name,
        data=payload.candles,
        symbol=payload.symbol,
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
        params=params,
    )
    validated_signals, _data_source = validate_signals(
        signals,
        symbol=payload.symbol,
        candles=payload.candles,
        candle_source="yahoo-finance",
    )
    serialized = [serialize_signal(s) for s in validated_signals]
    if not payload.include_diagnostics:
        return serialized

    diagnostics = diagnose_signal_run(
        signals,
        symbol=payload.symbol,
        candles=payload.candles,
        candle_source="yahoo-finance",
    )
    strategy = payload.strategy_name.lower()
    if strategy == "mtf" and ("htf_candles" not in params or "mtf_candles" not in params):
        diagnostics.insert(0, "MTF strategy needs htf_candles and mtf_candles for true multi-timeframe confirmation.")
    if strategy == "btst" and "daily_candles" not in params:
        diagnostics.insert(0, "BTST strategy works best with daily_candles and only validates near end of day.")
    if strategy in {"amd", "supply_demand"} and "htf_candles" not in params:
        diagnostics.insert(0, "Higher-timeframe candles were not supplied, so HTF confluence may reject strict setups.")

    return {
        "signals": serialized,
        "raw_signals": len(signals),
        "validated_signals": len(serialized),
        "diagnostics": diagnostics,
        "data_source": _data_source,
    }


@router.get("/strategies")
def list_strategies():
    return service.trading_engine.strategy_engine.available()
