from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks

from Backend.application.job_events import publish_job_update
from Backend.application.job_store import count_jobs, create_job, list_jobs, utc_now
from Backend.application.live_analysis_worker import LiveAnalysisPayload, execute_job

router = APIRouter()


def _present_job(job: dict) -> dict:
    if job.get("status") != "queued" or job.get("queued_at"):
        return job

    return {
        **job,
        "status": "stale",
        "note": "This job was queued before durable live-analysis jobs were enabled.",
    }


@router.get("/summary")
def summary():
    return {
        "status": "ready",
        "open_positions": 0,
        "active_jobs": count_jobs("running"),
        "total_jobs": count_jobs(),
        "updated_at": utc_now(),
    }


@router.post("/live-analysis/jobs")
def create_live_analysis_job(payload: LiveAnalysisPayload, background_tasks: BackgroundTasks):
    now = utc_now()
    job = {
        "job_id": str(uuid4()),
        "status": "queued",
        "symbol": payload.symbol.upper(),
        "strategy": payload.strategy,
        "interval": payload.interval,
        "period": payload.period,
        "created_at": now,
        "queued_at": now,
    }
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    created = create_job(job, payload_data)
    publish_job_update(created)
    background_tasks.add_task(execute_job, created["job_id"])
    return created


@router.get("/live-analysis/jobs")
def list_live_analysis_jobs():
    return {"jobs": [_present_job(job) for job in list_jobs()]}
