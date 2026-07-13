from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from Backend.application.backtest_jobs import cancel_backtest_job, get_backtest_job, list_backtest_jobs, start_backtest_job
from Backend.presentation.api.roles import require_roles
from Backend.application.subscriptions import require_entitlement


router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestStartRequest(BaseModel):
    symbol: str = "NIFTY"
    strategy_name: str = "amd"
    strategies: list[str] = Field(default_factory=lambda: ["amd", "breakout", "mean_reversion", "supply_demand"])
    capital: float = Field(default=100000, gt=0)
    risk_pct: float = Field(default=1.0, gt=0, le=10)
    rr_ratio: float = Field(default=2.0, gt=0, le=20)
    min_score: float = Field(default=0.0, ge=0)
    max_candles: int | None = Field(default=80, ge=10, le=100000)
    expected_seconds: float = Field(default=45.0, gt=0, le=3600)
    brokerage_per_order: float = Field(default=20.0, ge=0)
    brokerage_bps: float = Field(default=0.0, ge=0, le=1000)
    taxes_bps: float = Field(default=2.5, ge=0, le=1000)
    slippage_bps: float = Field(default=5.0, ge=0, le=1000)
    spread_bps: float = Field(default=8.0, ge=0, le=1000)
    entry_delay_seconds: int = Field(default=60, ge=0, le=3600)
    candles: list[dict[str, Any]] | None = Field(default=None)


@router.post("/start")
def start_backtest(
    payload: BacktestStartRequest,
    _access=Depends(require_entitlement("backtest.basic")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return start_backtest_job(payload_data)


@router.get("/history")
def backtest_history(
    limit: int = 20,
    _access=Depends(require_entitlement("backtest.basic")),
):
    return {"jobs": list_backtest_jobs(limit=limit)}


@router.get("/{job_id}")
def backtest_status(
    job_id: str,
    _access=Depends(require_entitlement("backtest.basic")),
):
    job = get_backtest_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest job not found.")
    return job


@router.post("/{job_id}/cancel")
def cancel_backtest(
    job_id: str,
    _access=Depends(require_entitlement("backtest.basic")),
):
    job = cancel_backtest_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest job not found.")
    return job
