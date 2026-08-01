from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from app.modules.portfolio.application.schemas.analytics import (
    AllocationResponse,
    AllocationSliceResponse,
    BenchmarkComparisonResponse,
    DiversificationScoreResponse,
    HealthScoreResponse,
    TopHoldingsResponse,
)
from app.modules.portfolio.domain.calculations.analytics import AnalyticsEngine
from app.modules.portfolio.domain.calculations.performance import PerformanceEngine
from app.modules.portfolio.domain.calculations.risk import RiskEngine
from app.modules.portfolio.domain.entities import HoldingSnapshot, PricePoint
from app.modules.portfolio.domain.exceptions import (
    InsufficientDataError,
    PortfolioNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import HoldingRepository, PortfolioRepository
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.models import PortfolioModel
from app.modules.portfolio.infrastructure.repositories.nav_snapshot_repository import (
    SqlAlchemyNavSnapshotRepository,
)


class AnalyticsService:
    """Use-case orchestration for portfolio composition analytics and health scoring."""

    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        holding_repository: HoldingRepository,
        nav_snapshot_repository: SqlAlchemyNavSnapshotRepository,
        market_data_provider: RedisMarketDataProvider,
    ) -> None:
        self._portfolios = portfolio_repository
        self._holdings = holding_repository
        self._nav_snapshots = nav_snapshot_repository
        self._market_data = market_data_provider

    async def _build_snapshots(self, portfolio_id: UUID) -> list[HoldingSnapshot]:
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
                    sector=h.sector,
                    asset_class=h.asset_class,
                    market_cap_segment=h.market_cap_segment,
                    beta=float(h.beta) if h.beta is not None else None,
                )
            )
        return snapshots

    async def sector_allocation(self, user_id: UUID, portfolio_id: UUID) -> AllocationResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        snapshots = await self._build_snapshots(portfolio_id)
        slices = AnalyticsEngine.sector_allocation(snapshots)
        return AllocationResponse(
            portfolio_id=str(portfolio_id),
            slices=[AllocationSliceResponse(label=s.label, value=s.value, weight_percent=s.weight_percent) for s in slices],
        )

    async def market_cap_allocation(self, user_id: UUID, portfolio_id: UUID) -> AllocationResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        snapshots = await self._build_snapshots(portfolio_id)
        slices = AnalyticsEngine.market_cap_allocation(snapshots)
        return AllocationResponse(
            portfolio_id=str(portfolio_id),
            slices=[AllocationSliceResponse(label=s.label, value=s.value, weight_percent=s.weight_percent) for s in slices],
        )

    async def asset_class_allocation(self, user_id: UUID, portfolio_id: UUID) -> AllocationResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        snapshots = await self._build_snapshots(portfolio_id)
        slices = AnalyticsEngine.asset_class_allocation(snapshots)
        return AllocationResponse(
            portfolio_id=str(portfolio_id),
            slices=[AllocationSliceResponse(label=s.label, value=s.value, weight_percent=s.weight_percent) for s in slices],
        )

    async def top_holdings(self, user_id: UUID, portfolio_id: UUID, limit: int = 5) -> TopHoldingsResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        snapshots = await self._build_snapshots(portfolio_id)
        top = AnalyticsEngine.top_holdings(snapshots, limit=limit)
        return TopHoldingsResponse(
            portfolio_id=str(portfolio_id),
            holdings=[AllocationSliceResponse(label=s.label, value=s.value, weight_percent=s.weight_percent) for s in top],
        )

    async def diversification_score(self, user_id: UUID, portfolio_id: UUID) -> DiversificationScoreResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        snapshots = await self._build_snapshots(portfolio_id)
        score = AnalyticsEngine.diversification_score(snapshots)
        return DiversificationScoreResponse(portfolio_id=str(portfolio_id), diversification_score=round(score, 2))

    async def health_score(self, user_id: UUID, portfolio_id: UUID) -> HealthScoreResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        snapshots = await self._build_snapshots(portfolio_id)

        volatility: float | None = None
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=365)
            nav_rows = await self._nav_snapshots.list_for_portfolio(
                portfolio_id, start_date=start_date, end_date=end_date
            )
            history = [PricePoint(as_of=r.as_of_date, close_price=float(r.nav_value)) for r in nav_rows]
            volatility = RiskEngine.volatility(history)
        except InsufficientDataError:
            volatility = None

        breakdown = AnalyticsEngine.health_score(snapshots, volatility_percent=volatility)
        return HealthScoreResponse(
            portfolio_id=str(portfolio_id),
            overall_score=breakdown.overall_score,
            diversification_component=breakdown.diversification_component,
            concentration_component=breakdown.concentration_component,
            volatility_component=breakdown.volatility_component,
            asset_mix_component=breakdown.asset_mix_component,
            notes=breakdown.notes,
        )

    async def benchmark_comparison(self, user_id: UUID, portfolio_id: UUID) -> BenchmarkComparisonResponse:
        portfolio = await self._get_owned_portfolio(user_id, portfolio_id)
        end_date = date.today()
        start_date = end_date - timedelta(days=365)

        nav_rows = await self._nav_snapshots.list_for_portfolio(
            portfolio_id, start_date=start_date, end_date=end_date
        )
        portfolio_history = [PricePoint(as_of=r.as_of_date, close_price=float(r.nav_value)) for r in nav_rows]

        try:
            portfolio_return = PerformanceEngine.absolute_return(portfolio_history)
        except InsufficientDataError:
            portfolio_return = 0.0

        benchmark_return = 0.0
        if portfolio.benchmark_symbol:
            try:
                raw = await self._market_data.get_price_history(
                    portfolio.benchmark_symbol, start_date, end_date
                )
                benchmark_history = [PricePoint(as_of=d, close_price=p) for d, p in raw]
                benchmark_return = PerformanceEngine.absolute_return(benchmark_history)
            except InsufficientDataError:
                benchmark_return = 0.0

        comparison = AnalyticsEngine.benchmark_comparison(portfolio_return, benchmark_return)
        return BenchmarkComparisonResponse(
            portfolio_id=str(portfolio_id),
            benchmark_symbol=portfolio.benchmark_symbol,
            portfolio_return_percent=round(comparison["portfolio_return_percent"], 4),
            benchmark_return_percent=round(comparison["benchmark_return_percent"], 4),
            excess_return_percent=round(comparison["excess_return_percent"], 4),
            outperforming=comparison["outperforming"],
        )

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio
