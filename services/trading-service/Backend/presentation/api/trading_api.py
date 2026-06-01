from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any

from Backend.application.dto import serialize_signal
from Backend.application.signal_validation import candle_freshness, diagnose_signal_run, validate_signals
from Backend.application.trading_service import TradingService
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.auth import current_user
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
    h1_candles: list[dict[str, Any]] | None = None
    h4_candles: list[dict[str, Any]] | None = None
    mtf_candles: list[dict[str, Any]] | None = None
    m15_candles: list[dict[str, Any]] | None = None
    m5_candles: list[dict[str, Any]] | None = None
    daily_candles: list[dict[str, Any]] | None = None
    candle_source: str | None = None
    include_diagnostics: bool = False


@router.post("/signals")
def generate_signals(
    payload: StrategyRunRequest,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
    request: Request = None,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    service = TradingService()
    candle_source = payload.candle_source or "yahoo-finance"
    params = {
        key: value
        for key, value in {
            "htf_candles": payload.htf_candles,
            "h1_candles": payload.h1_candles,
            "h4_candles": payload.h4_candles,
            "mtf_candles": payload.mtf_candles,
            "m15_candles": payload.m15_candles,
            "m5_candles": payload.m5_candles,
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
        candle_source=candle_source,
    )
    serialized = [serialize_signal(s) for s in validated_signals]
    if not payload.include_diagnostics:
        write_audit_log(
            db,
            action="signal_generated",
            actor=actor,
            target_type="strategy",
            target_id=payload.strategy_name,
            request=request,
            metadata={
                "symbol": payload.symbol,
                "raw_signals": len(signals),
                "validated_signals": len(serialized),
                "status": "generated" if serialized else "no_signal",
            },
        )
        return serialized

    diagnostics = diagnose_signal_run(
        signals,
        symbol=payload.symbol,
        candles=payload.candles,
        candle_source=candle_source,
    )
    strategy = payload.strategy_name.lower()
    if strategy == "mtf" and ("htf_candles" not in params or "mtf_candles" not in params):
        diagnostics.insert(0, "MTF strategy needs htf_candles and mtf_candles for true multi-timeframe confirmation.")
    if strategy == "btst" and "daily_candles" not in params:
        diagnostics.insert(0, "BTST strategy works best with daily_candles and only validates near end of day.")
    if strategy in {"amd", "supply_demand"} and "htf_candles" not in params:
        diagnostics.insert(0, "Higher-timeframe candles were not supplied, so HTF confluence may reject strict setups.")
    if strategy in {"cbt", "crt_tbs"} and not any(key in params for key in ("h1_candles", "h4_candles", "htf_candles")):
        diagnostics.insert(0, "CBT/CRT TBS works best with H4/H1 bias candles plus M15/M5 entry candles.")
    if strategy == "mtfa" and not all(key in params for key in ("h4_candles", "h1_candles", "m15_candles")):
        diagnostics.insert(0, "MTFA works best with explicit H4 compass, H1 bridge, and M15 trigger candles.")

    response = {
        "signals": serialized,
        "raw_signals": len(signals),
        "validated_signals": len(serialized),
        "diagnostics": diagnostics,
        "data_source": _data_source,
        "validation_context": candle_freshness(payload.candles),
    }
    write_audit_log(
        db,
        action="signal_generated",
        actor=actor,
        target_type="strategy",
        target_id=payload.strategy_name,
        request=request,
        metadata={
            "symbol": payload.symbol,
            "raw_signals": len(signals),
            "validated_signals": len(serialized),
            "status": "generated" if serialized else "no_signal",
        },
    )
    return response


@router.get("/strategies")
def list_strategies():
    service = TradingService()
    return service.trading_engine.strategy_engine.available()
