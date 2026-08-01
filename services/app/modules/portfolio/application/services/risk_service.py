from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from app.modules.portfolio.application.schemas.risk import RiskMetricsResponse
from app.modules.portfolio.domain.calculations.risk import RiskEngine
from app.modules.portfolio.domain.entities import PricePoint
from app.modules.portfolio.domain.exceptions import (
    InsufficientDataError,
    PortfolioNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import PortfolioRepository
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.models import PortfolioModel
from app.modules.portfolio.infrastructure.repositories.nav_snapshot_repository import (
    SqlAlchemyNavSnapshotRepository,
)

_RISK_FREE_RATE_ANNUAL_DEFAULT = 0.06
_LOOKBACK_DAYS_DEFAULT = 365


class RiskService:
    """Use-case orchestration for risk metrics, computed off NAV history vs. a benchmark."""

    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        nav_snapshot_repository: SqlAlchemyNavSnapshotRepository,
        market_data_provider: RedisMarketDataProvider,
    ) -> None:
        self._portfolios = portfolio_repository
        self._nav_snapshots = nav_snapshot_repository
        self._market_data = market_data_provider

    async def get_risk_metrics(
        self,
        user_id: UUID,
        portfolio_id: UUID,
        *,
        lookback_days: int = _LOOKBACK_DAYS_DEFAULT,
        risk_free_rate_annual: float = _RISK_FREE_RATE_ANNUAL_DEFAULT,
    ) -> RiskMetricsResponse:
        portfolio = await self._get_owned_portfolio(user_id, portfolio_id)
        warnings: list[str] = []

        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)
        nav_rows = await self._nav_snapshots.list_for_portfolio(
            portfolio_id, start_date=start_date, end_date=end_date
        )
        history = [PricePoint(as_of=row.as_of_date, close_price=float(row.nav_value)) for row in nav_rows]

        response = RiskMetricsResponse(
            portfolio_id=str(portfolio_id), benchmark_symbol=portfolio.benchmark_symbol
        )

        for attr, fn in (
            ("volatility_percent", lambda: RiskEngine.volatility(history)),
            ("sharpe_ratio", lambda: RiskEngine.sharpe_ratio(history, risk_free_rate_annual)),
            ("sortino_ratio", lambda: RiskEngine.sortino_ratio(history, risk_free_rate_annual)),
            ("max_drawdown_percent", lambda: RiskEngine.max_drawdown(history)),
        ):
            try:
                setattr(response, attr, round(fn(), 4))
            except InsufficientDataError as exc:
                warnings.append(f"{attr}: {exc.message}")

        if portfolio.benchmark_symbol:
            try:
                benchmark_history = await self._get_benchmark_history(
                    portfolio.benchmark_symbol, start_date, end_date
                )
                response.beta = round(RiskEngine.beta(history, benchmark_history), 4)
                response.alpha_percent = round(
                    RiskEngine.alpha(history, benchmark_history, risk_free_rate_annual), 4
                )
            except InsufficientDataError as exc:
                warnings.append(f"beta/alpha: {exc.message}")
        else:
            warnings.append("beta/alpha: portfolio has no benchmark_symbol configured.")

        response.warnings = warnings
        return response

    async def _get_benchmark_history(
        self, benchmark_symbol: str, start_date: date, end_date: date
    ) -> list[PricePoint]:
        raw = await self._market_data.get_price_history(benchmark_symbol, start_date, end_date)
        return [PricePoint(as_of=d, close_price=p) for d, p in raw]

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio
