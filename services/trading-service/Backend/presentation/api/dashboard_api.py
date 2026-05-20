from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from Backend.application.job_events import publish_job_update
from Backend.application.job_store import count_jobs, create_job, list_jobs, utc_now
from Backend.application.live_analysis_worker import LiveAnalysisPayload, execute_job
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.auth import current_user
from Backend.presentation.api.roles import require_roles

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
def summary(_role: str = Depends(require_roles("admin", "trader", "analyst", "viewer", "ops"))):
    return {
        "status": "ready",
        "open_positions": 0,
        "active_jobs": count_jobs("running"),
        "total_jobs": count_jobs(),
        "updated_at": utc_now(),
    }


@router.post("/live-analysis/jobs")
def create_live_analysis_job(
    payload: LiveAnalysisPayload,
    background_tasks: BackgroundTasks,
    request: Request,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
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
    write_audit_log(
        db,
        action="trading_job_created",
        actor=actor,
        target_type="job",
        target_id=created["job_id"],
        request=request,
        metadata={"symbol": job["symbol"], "strategy": job["strategy"]},
    )
    publish_job_update(created)
    background_tasks.add_task(execute_job, created["job_id"])
    return created


@router.get("/live-analysis/jobs")
def list_live_analysis_jobs(_role: str = Depends(require_roles("admin", "trader", "analyst", "viewer", "ops"))):
    return {"jobs": [_present_job(job) for job in list_jobs()]}
