from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from Backend.application.dto import serialize_signal
from Backend.application.trading_service import TradingService
from Backend.presentation.api.market_api import get_candles

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
JOBS_FILE = DATA_DIR / "dashboard_jobs.json"
service = TradingService()


class LiveAnalysisRequest(BaseModel):
    symbol: str
    interval: str = "1m"
    period: str = "1d"
    strategy: str = "breakout"
    capital: float = 100000
    risk_pct: float = 1
    rr_ratio: float = 2


def _load_jobs() -> dict[str, dict]:
    if not JOBS_FILE.exists():
        return {}

    try:
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_jobs(jobs: dict[str, dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_live_analysis(payload: LiveAnalysisRequest) -> dict[str, Any]:
    candles_response = get_candles(payload.symbol)
    candles = candles_response.get("candles", [])
    signals = service.run_strategy(
        strategy_name=payload.strategy,
        data=candles,
        symbol=payload.symbol.upper(),
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
    )
    return {
        "candles_analyzed": len(candles),
        "signals": [serialize_signal(signal) for signal in signals],
    }


def _present_job(job: dict) -> dict:
    if job.get("status") != "queued":
        return job

    return {
        **job,
        "status": "stale",
        "note": "This job was queued before live analysis execution was enabled.",
    }


@router.get("/summary")
def summary():
    jobs = _load_jobs()
    return {
        "status": "ready",
        "open_positions": 0,
        "active_jobs": sum(1 for job in jobs.values() if job.get("status") == "running"),
        "total_jobs": len(jobs),
        "updated_at": _utc_now(),
    }


@router.post("/live-analysis/jobs")
def create_live_analysis_job(payload: LiveAnalysisRequest):
    jobs = _load_jobs()
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "status": "running",
        "symbol": payload.symbol.upper(),
        "strategy": payload.strategy,
        "interval": payload.interval,
        "period": payload.period,
        "created_at": _utc_now(),
    }
    jobs[job_id] = job
    _save_jobs(jobs)

    try:
        result = _run_live_analysis(payload)
        job.update({
            "status": "completed",
            "completed_at": _utc_now(),
            "result": result,
        })
    except Exception as exc:
        job.update({
            "status": "failed",
            "completed_at": _utc_now(),
            "error": str(exc),
        })

    jobs[job_id] = job
    _save_jobs(jobs)
    return job


@router.get("/live-analysis/jobs")
def list_live_analysis_jobs():
    jobs = _load_jobs()
    return {
        "jobs": sorted(
            (_present_job(job) for job in jobs.values()),
            key=lambda job: job.get("created_at", ""),
            reverse=True,
        )
    }
