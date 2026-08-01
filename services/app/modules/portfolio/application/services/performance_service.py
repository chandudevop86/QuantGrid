from __future__ import annotations

from datetime import date
from uuid import UUID

from app.modules.portfolio.application.schemas.performance import PerformanceResponse
from app.modules.portfolio.domain.calculations.performance import PerformanceEngine
from app.modules.portfolio.domain.entities import CashFlow, PricePoint
from app.modules.portfolio.domain.enums import TransactionType
from app.modules.portfolio.domain.exceptions import (
    InsufficientDataError,
    PortfolioNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import HoldingRepository, PortfolioRepository, TransactionRepository
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.models import PortfolioModel
from app.modules.portfolio.infrastructure.repositories.nav_snapshot_repository import (
    SqlAlchemyNavSnapshotRepository,
)


class PerformanceService:
    """Use-case orchestration for time-window returns and money-weighted (XIRR) return."""

    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        transaction_repository: TransactionRepository,
        holding_repository: HoldingRepository,
        nav_snapshot_repository: SqlAlchemyNavSnapshotRepository,
        market_data_provider: RedisMarketDataProvider,
    ) -> None:
        self._portfolios = portfolio_repository
        self._transactions = transaction_repository
        self._holdings = holding_repository
        self._nav_snapshots = nav_snapshot_repository
        self._market_data = market_data_provider

    async def get_performance(
        self, user_id: UUID, portfolio_id: UUID, as_of: date | None = None
    ) -> PerformanceResponse:
        await self._get_owned_portfolio(user_id, portfolio_id)
        as_of = as_of or date.today()
        warnings: list[str] = []

        nav_rows = await self._nav_snapshots.list_for_portfolio(portfolio_id, end_date=as_of)
        history = [PricePoint(as_of=row.as_of_date, close_price=float(row.nav_value)) for row in nav_rows]

        response = PerformanceResponse(portfolio_id=str(portfolio_id), as_of=as_of)

        for attr, fn in (
            ("daily_return_percent", lambda: PerformanceEngine.daily_return(history, as_of)),
            ("weekly_return_percent", lambda: PerformanceEngine.weekly_return(history, as_of)),
            ("monthly_return_percent", lambda: PerformanceEngine.monthly_return(history, as_of)),
            ("yearly_return_percent", lambda: PerformanceEngine.yearly_return(history, as_of)),
            ("absolute_return_percent", lambda: PerformanceEngine.absolute_return(history)),
        ):
            try:
                setattr(response, attr, round(fn(), 4))
            except InsufficientDataError as exc:
                warnings.append(f"{attr}: {exc.message}")

        try:
            response.xirr_percent = round(await self._compute_xirr(portfolio_id, as_of), 4)
        except InsufficientDataError as exc:
            warnings.append(f"xirr_percent: {exc.message}")

        response.warnings = warnings
        return response

    async def _compute_xirr(self, portfolio_id: UUID, as_of: date) -> float:
        transactions = await self._transactions.list_all_for_portfolio(portfolio_id)
        cash_flows: list[CashFlow] = []
        for txn in transactions:
            if txn.transaction_date > as_of:
                continue
            if txn.transaction_type == TransactionType.BUY:
                amount = -(float(txn.quantity) * float(txn.price) + float(txn.fees))
            elif txn.transaction_type == TransactionType.SELL:
                amount = float(txn.quantity) * float(txn.price) - float(txn.fees)
            elif txn.transaction_type == TransactionType.DIVIDEND:
                amount = float(txn.price)
            else:  # BONUS / SPLIT are non-cash corporate actions
                continue
            cash_flows.append(CashFlow(when=txn.transaction_date, amount=amount))

        holdings = await self._holdings.list_all_for_portfolio(portfolio_id)
        terminal_value = 0.0
        for holding in holdings:
            try:
                price = await self._market_data.get_latest_price(holding.symbol)
            except InsufficientDataError:
                price = float(holding.average_cost)
            terminal_value += float(holding.quantity) * price
        if terminal_value > 0:
            cash_flows.append(CashFlow(when=as_of, amount=terminal_value))

        return PerformanceEngine.xirr(cash_flows)

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio
