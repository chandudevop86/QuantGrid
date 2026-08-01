from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_rebalancing_service
from app.modules.portfolio.application.schemas.rebalancing import RebalancingRequest, RebalancingResponse
from app.modules.portfolio.application.services.rebalancing_service import RebalancingService

router = APIRouter(prefix="/portfolios/{portfolio_id}/rebalancing", tags=["Rebalancing"])


@router.post("/suggestions", response_model=RebalancingResponse)
async def get_rebalancing_suggestions(
    portfolio_id: UUID,
    payload: RebalancingRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: RebalancingService = Depends(get_rebalancing_service),
) -> RebalancingResponse:
    """
    Compare current holding weights against a target allocation (symbol -> weight %)
    and return BUY/SELL/HOLD suggestions, subject to a drift-tolerance band.
    """
    return await service.suggest(current_user.id, portfolio_id, payload)
