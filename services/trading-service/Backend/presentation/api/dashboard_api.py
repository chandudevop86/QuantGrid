from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
JOBS_FILE = DATA_DIR / "dashboard_jobs.json"


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


@router.get("/summary")
def summary():
    jobs = _load_jobs()
    return {
        "status": "ready",
        "open_positions": 0,
        "active_jobs": sum(1 for job in jobs.values() if job.get("status") != "completed"),
        "total_jobs": len(jobs),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/live-analysis/jobs")
def create_live_analysis_job(payload: LiveAnalysisRequest):
    jobs = _load_jobs()
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "status": "queued",
        "symbol": payload.symbol,
        "strategy": payload.strategy,
        "interval": payload.interval,
        "period": payload.period,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    jobs[job_id] = job
    _save_jobs(jobs)
    return job


@router.get("/live-analysis/jobs")
def list_live_analysis_jobs():
    jobs = _load_jobs()
    return {"jobs": list(jobs.values())}
