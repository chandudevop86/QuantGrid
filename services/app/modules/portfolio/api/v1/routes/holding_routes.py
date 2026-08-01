from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import PageRequest, page_params
from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_holding_service
from app.modules.portfolio.application.schemas.common import MessageResponse, PaginatedResponse
from app.modules.portfolio.application.schemas.holding import (
    HoldingCreate,
    HoldingRead,
    HoldingUpdate,
    HoldingWithMarketData,
)
from app.modules.portfolio.application.services.holding_service import HoldingService

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["Holdings"])


@router.post("", response_model=HoldingRead, status_code=status.HTTP_201_CREATED)
async def create_holding(
    portfolio_id: UUID,
    payload: HoldingCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: HoldingService = Depends(get_holding_service),
) -> HoldingRead:
    """Manually create/update a holding's metadata (sector, asset class, etc.)."""
    return await service.create_holding(current_user.id, portfolio_id, payload)


@router.get("", response_model=PaginatedResponse[HoldingWithMarketData])
async def list_holdings(
    portfolio_id: UUID,
    page_request: PageRequest = Depends(page_params),
    sector: str | None = Query(default=None),
    sort_by: str = Query(default="symbol", pattern="^(symbol|quantity|average_cost|created_at)$"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    current_user: CurrentUser = Depends(get_current_user),
    service: HoldingService = Depends(get_holding_service),
) -> PaginatedResponse[HoldingWithMarketData]:
    return await service.list_holdings(
        current_user.id,
        portfolio_id,
        offset=page_request.offset,
        limit=page_request.limit,
        page=page_request.page,
        page_size=page_request.page_size,
        sector=sector,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/{holding_id}", response_model=HoldingWithMarketData)
async def get_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: HoldingService = Depends(get_holding_service),
) -> HoldingWithMarketData:
    return await service.get_holding(current_user.id, portfolio_id, holding_id)


@router.patch("/{holding_id}", response_model=HoldingRead)
async def update_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    payload: HoldingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: HoldingService = Depends(get_holding_service),
) -> HoldingRead:
    return await service.update_holding(current_user.id, portfolio_id, holding_id, payload)


@router.delete("/{holding_id}", response_model=MessageResponse)
async def delete_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: HoldingService = Depends(get_holding_service),
) -> MessageResponse:
    await service.delete_holding(current_user.id, portfolio_id, holding_id)
    return MessageResponse(message="Holding deleted.")
