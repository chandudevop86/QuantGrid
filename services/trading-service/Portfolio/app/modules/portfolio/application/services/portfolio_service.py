from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.portfolio.application.schemas.common import PaginatedResponse
from app.modules.portfolio.application.schemas.portfolio import (
    PortfolioCreate,
    PortfolioRead,
    PortfolioSummary,
    PortfolioUpdate,
)
from app.modules.portfolio.domain.exceptions import (
    DuplicatePortfolioNameError,
    PortfolioNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import HoldingRepository, PortfolioRepository
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.models import PortfolioModel


class PortfolioService:
    """Use-case orchestration for Portfolio CRUD, independent of the transport layer."""

    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        holding_repository: HoldingRepository,
        market_data_provider: RedisMarketDataProvider,
    ) -> None:
        self._portfolios = portfolio_repository
        self._holdings = holding_repository
        self._market_data = market_data_provider

    async def create_portfolio(self, user_id: UUID, payload: PortfolioCreate) -> PortfolioRead:
        existing = await self._portfolios.get_by_name_for_user(user_id, payload.name)
        if existing is not None:
            raise DuplicatePortfolioNameError(payload.name)
        portfolio = await self._portfolios.create(
            user_id=user_id,
            name=payload.name,
            description=payload.description,
            portfolio_type=payload.portfolio_type,
            base_currency=payload.base_currency,
            benchmark_symbol=payload.benchmark_symbol,
        )
        return PortfolioRead.model_validate(portfolio)

    async def get_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioRead:
        portfolio = await self._get_owned_portfolio(user_id, portfolio_id)
        return PortfolioRead.model_validate(portfolio)

    async def get_portfolio_summary(self, user_id: UUID, portfolio_id: UUID) -> PortfolioSummary:
        portfolio = await self._get_owned_portfolio(user_id, portfolio_id)
        holdings = await self._holdings.list_all_for_portfolio(portfolio_id)

        total_market_value = Decimal("0")
        total_invested_value = Decimal("0")
        for holding in holdings:
            invested = holding.quantity * holding.average_cost
            total_invested_value += invested
            try:
                price = Decimal(str(await self._market_data.get_latest_price(holding.symbol)))
            except Exception:
                price = holding.average_cost  # graceful degradation if quote unavailable
            total_market_value += holding.quantity * price

        pnl = total_market_value - total_invested_value
        pnl_percent = float(pnl / total_invested_value * 100) if total_invested_value else 0.0

        return PortfolioSummary(
            id=portfolio.id,
            name=portfolio.name,
            portfolio_type=portfolio.portfolio_type,
            base_currency=portfolio.base_currency,
            total_market_value=total_market_value,
            total_invested_value=total_invested_value,
            total_unrealized_pnl=pnl,
            total_unrealized_pnl_percent=pnl_percent,
            holdings_count=len(holdings),
        )

    async def list_portfolios(
        self,
        user_id: UUID,
        *,
        offset: int,
        limit: int,
        page: int,
        page_size: int,
        portfolio_type: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> PaginatedResponse[PortfolioRead]:
        portfolios = await self._portfolios.list_for_user(
            user_id,
            offset=offset,
            limit=limit,
            portfolio_type=portfolio_type,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total = await self._portfolios.count_for_user(user_id, portfolio_type=portfolio_type)
        return PaginatedResponse.build(
            items=[PortfolioRead.model_validate(p) for p in portfolios],
            page=page,
            page_size=page_size,
            total_items=total,
        )

    async def update_portfolio(
        self, user_id: UUID, portfolio_id: UUID, payload: PortfolioUpdate
    ) -> PortfolioRead:
        portfolio = await self._get_owned_portfolio(user_id, portfolio_id)
        if payload.name and payload.name != portfolio.name:
            existing = await self._portfolios.get_by_name_for_user(user_id, payload.name)
            if existing is not None:
                raise DuplicatePortfolioNameError(payload.name)
        updated = await self._portfolios.update(
            portfolio, **payload.model_dump(exclude_unset=True, exclude_none=True)
        )
        return PortfolioRead.model_validate(updated)

    async def delete_portfolio(self, user_id: UUID, portfolio_id: UUID) -> None:
        portfolio = await self._get_owned_portfolio(user_id, portfolio_id)
        await self._portfolios.delete(portfolio)

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio
