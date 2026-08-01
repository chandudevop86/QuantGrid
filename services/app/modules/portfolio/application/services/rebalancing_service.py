from __future__ import annotations

from uuid import UUID

from app.modules.portfolio.application.schemas.rebalancing import (
    RebalancingRequest,
    RebalancingResponse,
    RebalancingSuggestionResponse,
)
from app.modules.portfolio.domain.calculations.rebalancing import RebalancingEngine
from app.modules.portfolio.domain.entities import HoldingSnapshot
from app.modules.portfolio.domain.exceptions import (
    InsufficientDataError,
    PortfolioNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import HoldingRepository, PortfolioRepository
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.models import PortfolioModel


class RebalancingService:
    """Use-case orchestration for target-weight-based rebalancing suggestions."""

    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        holding_repository: HoldingRepository,
        market_data_provider: RedisMarketDataProvider,
    ) -> None:
        self._portfolios = portfolio_repository
        self._holdings = holding_repository
        self._market_data = market_data_provider

    async def suggest(
        self, user_id: UUID, portfolio_id: UUID, payload: RebalancingRequest
    ) -> RebalancingResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        holdings = await self._holdings.list_all_for_portfolio(portfolio_id)

        snapshots: list[HoldingSnapshot] = []
        for h in holdings:
            try:
                price = await self._market_data.get_latest_price(h.symbol)
            except InsufficientDataError:
                price = float(h.average_cost)
            snapshots.append(
                HoldingSnapshot(
                    symbol=h.symbol,
                    quantity=float(h.quantity),
                    average_cost=float(h.average_cost),
                    current_price=price,
                )
            )

        suggestions = RebalancingEngine.suggest(
            snapshots, payload.target_weights, drift_tolerance_percent=payload.drift_tolerance_percent
        )
        return RebalancingResponse(
            portfolio_id=str(portfolio_id),
            suggestions=[
                RebalancingSuggestionResponse(
                    symbol=s.symbol,
                    current_weight_percent=s.current_weight_percent,
                    target_weight_percent=s.target_weight_percent,
                    drift_percent=s.drift_percent,
                    action=s.action,
                    suggested_amount=s.suggested_amount,
                )
                for s in suggestions
            ],
        )

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio
