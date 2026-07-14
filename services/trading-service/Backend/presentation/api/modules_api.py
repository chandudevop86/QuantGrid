from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from Backend.application.quant_modules import (
    backtesting_comparison,
    backtesting_module,
    historical_option_chain,
    _live_nse_fallback_payload,
    live_nse_option_chain,
    module_dashboard,
    option_chain_engine,
    risk_engine_summary,
    trade_journal_summary,
)
from Backend.presentation.api.roles import require_roles
from Backend.application.subscriptions import require_entitlement


router = APIRouter(prefix="/modules", tags=["modules"])
logger = logging.getLogger("quantgrid.modules")


class BacktestModuleRequest(BaseModel):
    symbol: str = "NIFTY"
    strategy_name: str = "amd"
    capital: float = 100000
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    min_score: float = 0.0
    max_candles: int | None = None
    candles: list[dict[str, Any]] | None = Field(default=None)


class BacktestComparisonRequest(BacktestModuleRequest):
    strategies: list[str] = Field(default_factory=lambda: ["amd", "breakout", "btst", "cbt", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"])


def _module_option_chain_payload(payload: dict[str, Any], *, legacy_source: bool = False) -> dict[str, Any]:
    return payload


@router.get("/option-chain/{symbol}")
def option_chain_module(
    symbol: str,
    strikes_each_side: int = 5,
    step: int = 50,
    _access=Depends(require_entitlement("options.basic")),
):
    try:
        return _module_option_chain_payload(
            option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step),
            legacy_source=True,
        )
    except Exception as exc:
        logger.exception("option_chain_module_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        payload = option_chain_engine("NIFTY", strikes_each_side=strikes_each_side, step=step)
        return _module_option_chain_payload(_live_nse_fallback_payload(payload, exc), legacy_source=True)


@router.get("/option-chain/{symbol}/live-nse")
def live_nse_option_chain_module(
    symbol: str,
    strikes_each_side: int = 8,
    step: int = 50,
    _access=Depends(require_entitlement("options.advanced")),
):
    try:
        return _module_option_chain_payload(live_nse_option_chain(symbol, strikes_each_side=strikes_each_side, step=step))
    except Exception as exc:
        logger.exception("live_nse_option_chain_module_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        payload = option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step)
        return _module_option_chain_payload(
            _live_nse_fallback_payload(payload, exc),
            legacy_source="provider unavailable" in str(exc).lower(),
        )


@router.get("/option-chain/{symbol}/historical")
def historical_option_chain_module(
    symbol: str,
    periods: int = 12,
    step: int = 50,
    _access=Depends(require_entitlement("options.advanced")),
):
    return historical_option_chain(symbol, periods=periods, step=step)


@router.post("/backtesting")
def run_backtesting_module(
    payload: BacktestModuleRequest,
    _access=Depends(require_entitlement("backtest.basic")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return backtesting_module(payload_data)


@router.post("/backtesting/comparison")
def run_backtesting_comparison(
    payload: BacktestComparisonRequest,
    _access=Depends(require_entitlement("backtest.advanced")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return backtesting_comparison(payload_data)


@router.get("/risk-engine")
def get_risk_engine_module(_access=Depends(require_entitlement("risk.advanced"))):
    return risk_engine_summary()


@router.get("/trade-journal")
def get_trade_journal_module(
    limit: int = 100,
    _access=Depends(require_entitlement("export.csv")),
):
    return trade_journal_summary(limit=max(1, min(int(limit), 500)))


@router.get("/dashboard")
def get_modules_dashboard(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    return module_dashboard()
