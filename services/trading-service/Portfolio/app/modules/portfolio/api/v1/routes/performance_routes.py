from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_performance_service
from app.modules.portfolio.application.schemas.performance import PerformanceResponse
from app.modules.portfolio.application.services.performance_service import PerformanceService

router = APIRouter(prefix="/portfolios/{portfolio_id}/performance", tags=["Performance"])


@router.get("", response_model=PerformanceResponse)
async def get_performance(
    portfolio_id: UUID,
    as_of: date | None = Query(default=None, description="Defaults to today."),
    current_user: CurrentUser = Depends(get_current_user),
    service: PerformanceService = Depends(get_performance_service),
) -> PerformanceResponse:
    """Daily / weekly / monthly / yearly / absolute return, and money-weighted XIRR."""
    return await service.get_performance(current_user.id, portfolio_id, as_of)
