from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_analytics_service
from app.modules.portfolio.application.schemas.analytics import (
    AllocationResponse,
    BenchmarkComparisonResponse,
    DiversificationScoreResponse,
    HealthScoreResponse,
    TopHoldingsResponse,
)
from app.modules.portfolio.application.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/portfolios/{portfolio_id}/analytics", tags=["Analytics"])


@router.get("/sector-allocation", response_model=AllocationResponse)
async def sector_allocation(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AllocationResponse:
    return await service.sector_allocation(current_user.id, portfolio_id)


@router.get("/market-cap-allocation", response_model=AllocationResponse)
async def market_cap_allocation(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AllocationResponse:
    return await service.market_cap_allocation(current_user.id, portfolio_id)


@router.get("/asset-allocation", response_model=AllocationResponse)
async def asset_class_allocation(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AllocationResponse:
    return await service.asset_class_allocation(current_user.id, portfolio_id)


@router.get("/top-holdings", response_model=TopHoldingsResponse)
async def top_holdings(
    portfolio_id: UUID,
    limit: int = Query(default=5, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> TopHoldingsResponse:
    return await service.top_holdings(current_user.id, portfolio_id, limit=limit)


@router.get("/diversification-score", response_model=DiversificationScoreResponse)
async def diversification_score(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> DiversificationScoreResponse:
    return await service.diversification_score(current_user.id, portfolio_id)


@router.get("/health-score", response_model=HealthScoreResponse)
async def health_score(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> HealthScoreResponse:
    return await service.health_score(current_user.id, portfolio_id)


@router.get("/benchmark-comparison", response_model=BenchmarkComparisonResponse)
async def benchmark_comparison(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> BenchmarkComparisonResponse:
    return await service.benchmark_comparison(current_user.id, portfolio_id)
