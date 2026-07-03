from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from Backend.application.institutional_dashboard import build_institutional_dashboard
from Backend.presentation.api.roles import require_roles

router = APIRouter(prefix="/institutional", tags=["institutional"])


@router.get("/dashboard")
def institutional_dashboard(
    symbol: str = "NIFTY",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
) -> dict[str, Any]:
    option_chain = None
    option_chain_error = None
    try:
        from Backend.presentation.api.market_api import get_option_chain

        option_chain = get_option_chain(symbol, _role=_role)
    except Exception as exc:
        option_chain_error = str(exc)

    return build_institutional_dashboard(
        symbol,
        option_chain=option_chain,
        option_chain_error=option_chain_error,
    )
