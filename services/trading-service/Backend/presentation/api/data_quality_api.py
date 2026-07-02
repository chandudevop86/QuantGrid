from __future__ import annotations

from fastapi import APIRouter, Depends

from Backend.application.data_quality_service import build_data_quality_dashboard
from Backend.presentation.api.roles import require_roles

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


@router.get("/dashboard")
def data_quality_dashboard(
    symbol: str = "NIFTY",
    interval: str = "1m",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    return build_data_quality_dashboard(symbol=symbol, interval=interval)
