from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.application.job_queue import enqueue_job
from Backend.application.notifications import get_notification_settings, send_alert
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.auth import current_user, require_roles

router = APIRouter(prefix="/admin/notifications", tags=["notifications"])


class NotificationJobRequest(BaseModel):
    subject: str = Field(default="QuantGrid notification", min_length=1)
    message: str = Field(min_length=1)


@router.get("/status")
def notification_status(_role: str = Depends(require_roles("admin", "developer"))) -> dict[str, object]:
    settings = get_notification_settings()
    return {
        "alerts_enabled": settings.enabled,
        "channels": {
            "telegram": settings.telegram_enabled,
            "slack": settings.slack_enabled,
            "email": settings.email_enabled,
        },
        "configured_recipients": {
            "telegram_chat": bool(settings.telegram_chat_id),
            "email_recipients": len(settings.smtp_to),
        },
    }


@router.post("/test")
def send_test_notification(_role: str = Depends(require_roles("admin", "developer"))) -> dict[str, str]:
    send_alert(
        "QuantGrid test alert",
        "QuantGrid test alert\nNotifications are configured and reachable from the backend.",
    )
    return {"status": "sent"}


@router.post("/jobs")
def enqueue_notification_job(
    payload: NotificationJobRequest,
    request: Request,
    _role: str = Depends(require_roles("admin", "developer", "ops")),
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    job = enqueue_job(
        "notification",
        payload_data,
        metadata={"subject": payload.subject},
    )
    write_audit_log(
        db,
        action="trading_job_created",
        actor=actor,
        target_type="job",
        target_id=job["job_id"],
        request=request,
        metadata={"job_type": "notification", "status": "queued"},
    )
    return job
