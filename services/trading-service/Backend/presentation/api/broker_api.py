from __future__ import annotations

from fastapi import APIRouter, Depends

from Backend.core.config import get_settings
from Backend.infrastructure.broker.dhan_status import check_dhan_profile
from Backend.presentation.api.roles import require_roles


router = APIRouter(tags=["broker"])


@router.get("/status")
def broker_status(_role: str = Depends(require_roles("admin", "trader", "ops"))):
    settings = get_settings()
    provider = settings.broker_provider or "none"

    if provider == "dhan":
        status = check_dhan_profile()
    elif provider == "none":
        status = {
            "provider": "none",
            "configured": False,
            "connected": False,
            "paper_mode": True,
            "message": "No broker is configured. QuantGrid is running in paper mode.",
        }
    else:
        status = {
            "provider": provider,
            "configured": settings.broker_configured,
            "connected": False,
            "paper_mode": True,
            "message": f"Broker status check is not implemented for {provider}.",
        }

    status["live_trading_enabled"] = settings.live_trading_enabled
    status["real_money_orders_enabled"] = False
    return status
