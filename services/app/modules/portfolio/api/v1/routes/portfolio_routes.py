from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import PageRequest, page_params
from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_portfolio_service
from app.modules.portfolio.application.schemas.common import MessageResponse, PaginatedResponse
from app.modules.portfolio.application.schemas.portfolio import (
    PortfolioCreate,
    PortfolioRead,
    PortfolioSummary,
    PortfolioUpdate,
)
from app.modules.portfolio.application.services.portfolio_service import PortfolioService
from app.modules.portfolio.domain.enums import PortfolioType

router = APIRouter(prefix="/portfolios", tags=["Portfolios"])


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioRead:
    """Create a new portfolio for the authenticated user."""
    return await service.create_portfolio(current_user.id, payload)


@router.get("", response_model=PaginatedResponse[PortfolioRead])
async def list_portfolios(
    page_request: PageRequest = Depends(page_params),
    portfolio_type: PortfolioType | None = Query(default=None),
    sort_by: str = Query(default="created_at", pattern="^(name|created_at|updated_at)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PaginatedResponse[PortfolioRead]:
    """List the authenticated user's portfolios, paginated/filterable/sortable."""
    return await service.list_portfolios(
        current_user.id,
        offset=page_request.offset,
        limit=page_request.limit,
        page=page_request.page,
        page_size=page_request.page_size,
        portfolio_type=portfolio_type.value if portfolio_type else None,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/{portfolio_id}", response_model=PortfolioRead)
async def get_portfolio(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioRead:
    return await service.get_portfolio(current_user.id, portfolio_id)


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioSummary:
    """Portfolio metadata enriched with live valuation totals (market value, P&L)."""
    return await service.get_portfolio_summary(current_user.id, portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
async def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioRead:
    return await service.update_portfolio(current_user.id, portfolio_id, payload)


@router.delete("/{portfolio_id}", response_model=MessageResponse)
async def delete_portfolio(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> MessageResponse:
    await service.delete_portfolio(current_user.id, portfolio_id)
    return MessageResponse(message="Portfolio deleted.")
