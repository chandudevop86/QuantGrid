from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from Backend.application.quant_modules import (
    backtesting_module,
    historical_option_chain,
    live_nse_option_chain,
    module_dashboard,
    option_chain_engine,
    risk_engine_summary,
    trade_journal_summary,
)
from Backend.presentation.api.roles import require_roles


router = APIRouter(prefix="/modules", tags=["modules"])


class BacktestModuleRequest(BaseModel):
    symbol: str = "NIFTY"
    strategy_name: str = "amd"
    capital: float = 100000
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    min_score: float = 0.0
    candles: list[dict[str, Any]] | None = Field(default=None)


@router.get("/option-chain/{symbol}")
def option_chain_module(
    symbol: str,
    strikes_each_side: int = 5,
    step: int = 50,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    return option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step)


@router.get("/option-chain/{symbol}/live-nse")
def live_nse_option_chain_module(
    symbol: str,
    strikes_each_side: int = 8,
    step: int = 50,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    try:
        return live_nse_option_chain(symbol, strikes_each_side=strikes_each_side, step=step)
    except Exception as exc:
        payload = option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step)
        return {
            **payload,
            "module": "live_nse_option_chain",
            "source": "synthetic-demo-chain",
            "warning": f"Live NSE option-chain unavailable: {exc}. Showing synthetic fallback.",
            "signals": {
                "bias": "NEUTRAL",
                "reason": "Live NSE option-chain is unavailable; synthetic fallback is for display only.",
                "total_call_oi": int(sum(float(row["ce"].get("oi") or 0) for row in payload["rows"])),
                "total_put_oi": int(sum(float(row["pe"].get("oi") or 0) for row in payload["rows"])),
                "pcr": payload.get("pcr"),
                "atm_strike": payload.get("atm_strike"),
                "max_pain": payload.get("max_pain"),
            },
        }


@router.get("/option-chain/{symbol}/historical")
def historical_option_chain_module(
    symbol: str,
    periods: int = 12,
    step: int = 50,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    return historical_option_chain(symbol, periods=periods, step=step)


@router.post("/backtesting")
def run_backtesting_module(
    payload: BacktestModuleRequest,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return backtesting_module(payload_data)


@router.get("/risk-engine")
def get_risk_engine_module(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    return risk_engine_summary()


@router.get("/trade-journal")
def get_trade_journal_module(
    limit: int = 100,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    return trade_journal_summary(limit=max(1, min(int(limit), 500)))


@router.get("/dashboard")
def get_modules_dashboard(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    return module_dashboard()
