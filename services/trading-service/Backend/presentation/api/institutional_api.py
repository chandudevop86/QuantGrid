from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from Backend.application.institutional_dashboard import build_institutional_dashboard
from Backend.presentation.api.roles import require_roles
from Backend.application.subscriptions import require_entitlement

router = APIRouter(prefix="/institutional", tags=["institutional"])


@router.get("/dashboard")
def institutional_dashboard(
    symbol: str = "NIFTY",
    _access=Depends(require_entitlement("institutional.flow")),
) -> dict[str, Any]:
    option_chain = None
    option_chain_error = None
    try:
        from Backend.presentation.api.market_api import get_option_chain

        option_chain = get_option_chain(symbol, _role=_access.user.role)
    except Exception as exc:
        option_chain_error = str(exc)

    return build_institutional_dashboard(
        symbol,
        option_chain=option_chain,
        option_chain_error=option_chain_error,
    )
