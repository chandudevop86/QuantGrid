from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from Backend.application.backtest_jobs import cancel_backtest_job, get_backtest_job, list_backtest_jobs, start_backtest_job
from Backend.presentation.api.roles import require_roles


router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestStartRequest(BaseModel):
    symbol: str = "NIFTY"
    strategy_name: str = "amd"
    strategies: list[str] = Field(default_factory=lambda: ["amd", "breakout", "mean_reversion", "supply_demand"])
    capital: float = 100000
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    min_score: float = 0.0
    max_candles: int | None = 80
    expected_seconds: float = 45.0
    candles: list[dict[str, Any]] | None = Field(default=None)


@router.post("/start")
def start_backtest(
    payload: BacktestStartRequest,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return start_backtest_job(payload_data)


@router.get("/history")
def backtest_history(
    limit: int = 20,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    return {"jobs": list_backtest_jobs(limit=limit)}


@router.get("/{job_id}")
def backtest_status(
    job_id: str,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    job = get_backtest_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest job not found.")
    return job


@router.post("/{job_id}/cancel")
def cancel_backtest(
    job_id: str,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    job = cancel_backtest_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest job not found.")
    return job
