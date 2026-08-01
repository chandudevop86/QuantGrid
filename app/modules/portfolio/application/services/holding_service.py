from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.portfolio.application.schemas.common import PaginatedResponse
from app.modules.portfolio.application.schemas.holding import (
    HoldingCreate,
    HoldingRead,
    HoldingUpdate,
    HoldingWithMarketData,
)
from app.modules.portfolio.domain.exceptions import (
    HoldingNotFoundError,
    PortfolioNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import HoldingRepository, PortfolioRepository
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.models import HoldingModel, PortfolioModel


class HoldingService:
    """Use-case orchestration for Holding CRUD (metadata) within an owned portfolio."""

    def __init__(
        self,
        holding_repository: HoldingRepository,
        portfolio_repository: PortfolioRepository,
        market_data_provider: RedisMarketDataProvider,
    ) -> None:
        self._holdings = holding_repository
        self._portfolios = portfolio_repository
        self._market_data = market_data_provider

    async def create_holding(
        self, user_id: UUID, portfolio_id: UUID, payload: HoldingCreate
    ) -> HoldingRead:
        await self._get_owned_portfolio(user_id, portfolio_id)
        existing = await self._holdings.get_by_symbol(portfolio_id, payload.symbol)
        if existing is not None:
            # Idempotent-ish: merge into existing holding's metadata rather than erroring,
            # since quantity/cost is normally driven by transactions, not manual entry.
            updated = await self._holdings.update(
                existing, **payload.model_dump(exclude={"symbol"}, exclude_unset=True)
            )
            return HoldingRead.model_validate(updated)
        holding = await self._holdings.create(portfolio_id=portfolio_id, **payload.model_dump())
        return HoldingRead.model_validate(holding)

    async def get_holding(self, user_id: UUID, portfolio_id: UUID, holding_id: UUID) -> HoldingWithMarketData:
        await self._get_owned_portfolio(user_id, portfolio_id)
        holding = await self._get_holding_in_portfolio(portfolio_id, holding_id)
        return await self._enrich(holding)

    async def list_holdings(
        self,
        user_id: UUID,
        portfolio_id: UUID,
        *,
        offset: int,
        limit: int,
        page: int,
        page_size: int,
        sector: str | None = None,
        sort_by: str = "symbol",
        sort_dir: str = "asc",
    ) -> PaginatedResponse[HoldingWithMarketData]:
        await self._get_owned_portfolio(user_id, portfolio_id)
        holdings = await self._holdings.list_for_portfolio(
            portfolio_id, offset=offset, limit=limit, sector=sector, sort_by=sort_by, sort_dir=sort_dir
        )
        total = await self._holdings.count_for_portfolio(portfolio_id, sector=sector)
        enriched = [await self._enrich(h) for h in holdings]
        return PaginatedResponse.build(items=enriched, page=page, page_size=page_size, total_items=total)

    async def update_holding(
        self, user_id: UUID, portfolio_id: UUID, holding_id: UUID, payload: HoldingUpdate
    ) -> HoldingRead:
        await self._get_owned_portfolio(user_id, portfolio_id)
        holding = await self._get_holding_in_portfolio(portfolio_id, holding_id)
        updated = await self._holdings.update(holding, **payload.model_dump(exclude_unset=True))
        return HoldingRead.model_validate(updated)

    async def delete_holding(self, user_id: UUID, portfolio_id: UUID, holding_id: UUID) -> None:
        await self._get_owned_portfolio(user_id, portfolio_id)
        holding = await self._get_holding_in_portfolio(portfolio_id, holding_id)
        await self._holdings.delete(holding)

    async def _enrich(self, holding: HoldingModel) -> HoldingWithMarketData:
        current_price: Decimal | None
        try:
            current_price = Decimal(str(await self._market_data.get_latest_price(holding.symbol)))
        except Exception:
            current_price = None

        invested_value = holding.quantity * holding.average_cost
        market_value = holding.quantity * current_price if current_price is not None else None
        pnl = (market_value - invested_value) if market_value is not None else None
        pnl_percent = (
            float(pnl / invested_value * 100) if pnl is not None and invested_value else None
        )
        return HoldingWithMarketData(
            **HoldingRead.model_validate(holding).model_dump(),
            current_price=current_price,
            market_value=market_value,
            invested_value=invested_value,
            unrealized_pnl=pnl,
            unrealized_pnl_percent=pnl_percent,
        )

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio

    async def _get_holding_in_portfolio(self, portfolio_id: UUID, holding_id: UUID) -> HoldingModel:
        holding = await self._holdings.get_by_id(holding_id)
        if holding is None or holding.portfolio_id != portfolio_id:
            raise HoldingNotFoundError(holding_id)
        return holding
