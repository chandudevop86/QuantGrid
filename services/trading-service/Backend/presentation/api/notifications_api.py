from __future__ import annotations

from fastapi import APIRouter, Depends

from Backend.application.notifications import get_notification_settings, send_alert
from Backend.presentation.api.auth import require_roles

router = APIRouter(prefix="/admin/notifications", tags=["notifications"])


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
