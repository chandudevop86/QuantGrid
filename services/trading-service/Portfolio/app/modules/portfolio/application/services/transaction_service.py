from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.modules.portfolio.application.schemas.common import PaginatedResponse
from app.modules.portfolio.application.schemas.transaction import TransactionCreate, TransactionRead
from app.modules.portfolio.domain.calculations.position_engine import PositionEngine, PositionState
from app.modules.portfolio.domain.enums import TransactionType
from app.modules.portfolio.domain.exceptions import (
    InvalidTransactionError,
    PortfolioNotFoundError,
    TransactionNotFoundError,
    UnauthorizedPortfolioAccessError,
)
from app.modules.portfolio.domain.repositories import HoldingRepository, PortfolioRepository, TransactionRepository
from app.modules.portfolio.infrastructure.models import HoldingModel, PortfolioModel, TransactionModel


class TransactionService:
    """
    Use-case orchestration for recording and querying portfolio transactions.

    Every mutating transaction (BUY/SELL/BONUS/SPLIT) folds through the pure
    `PositionEngine`, and the resulting `HoldingModel` (quantity / weighted
    average cost) is kept in sync transactionally alongside the transaction
    record itself.
    """

    def __init__(
        self,
        transaction_repository: TransactionRepository,
        holding_repository: HoldingRepository,
        portfolio_repository: PortfolioRepository,
    ) -> None:
        self._transactions = transaction_repository
        self._holdings = holding_repository
        self._portfolios = portfolio_repository

    async def record_transaction(
        self, user_id: UUID, portfolio_id: UUID, payload: TransactionCreate
    ) -> TransactionRead:
        await self._get_owned_portfolio(user_id, portfolio_id)

        holding = await self._holdings.get_by_symbol(portfolio_id, payload.symbol)
        if holding is None:
            if payload.transaction_type != TransactionType.BUY:
                raise InvalidTransactionError(
                    f"Cannot record a {payload.transaction_type.value} for '{payload.symbol}': "
                    "no existing holding. Record a BUY first."
                )
            holding = await self._holdings.create(
                portfolio_id=portfolio_id,
                symbol=payload.symbol,
                quantity=Decimal("0"),
                average_cost=Decimal("0"),
            )

        state = PositionState(
            quantity=float(holding.quantity), average_cost=float(holding.average_cost)
        )
        new_state = PositionEngine.apply(
            state,
            symbol=payload.symbol,
            transaction_type=payload.transaction_type,
            quantity=float(payload.quantity),
            price=float(payload.price),
            fees=float(payload.fees),
            split_ratio_from=float(payload.split_ratio_from) if payload.split_ratio_from else None,
            split_ratio_to=float(payload.split_ratio_to) if payload.split_ratio_to else None,
        )

        await self._holdings.update(
            holding,
            quantity=Decimal(str(round(new_state.quantity, 6))),
            average_cost=Decimal(str(round(new_state.average_cost, 6))),
        )

        transaction = await self._transactions.create(
            portfolio_id=portfolio_id,
            symbol=payload.symbol,
            transaction_type=payload.transaction_type,
            quantity=payload.quantity,
            price=payload.price,
            fees=payload.fees,
            transaction_date=payload.transaction_date,
            split_ratio_from=payload.split_ratio_from,
            split_ratio_to=payload.split_ratio_to,
            notes=payload.notes,
        )
        return TransactionRead.model_validate(transaction)

    async def get_transaction(
        self, user_id: UUID, portfolio_id: UUID, transaction_id: UUID
    ) -> TransactionRead:
        await self._get_owned_portfolio(user_id, portfolio_id)
        transaction = await self._get_transaction_in_portfolio(portfolio_id, transaction_id)
        return TransactionRead.model_validate(transaction)

    async def list_transactions(
        self,
        user_id: UUID,
        portfolio_id: UUID,
        *,
        offset: int,
        limit: int,
        page: int,
        page_size: int,
        symbol: str | None = None,
        transaction_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        sort_by: str = "transaction_date",
        sort_dir: str = "desc",
    ) -> PaginatedResponse[TransactionRead]:
        await self._get_owned_portfolio(user_id, portfolio_id)
        transactions = await self._transactions.list_for_portfolio(
            portfolio_id,
            offset=offset,
            limit=limit,
            symbol=symbol,
            transaction_type=transaction_type,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total = await self._transactions.count_for_portfolio(
            portfolio_id,
            symbol=symbol,
            transaction_type=transaction_type,
            start_date=start_date,
            end_date=end_date,
        )
        return PaginatedResponse.build(
            items=[TransactionRead.model_validate(t) for t in transactions],
            page=page,
            page_size=page_size,
            total_items=total,
        )

    async def delete_transaction(
        self, user_id: UUID, portfolio_id: UUID, transaction_id: UUID
    ) -> None:
        await self._get_owned_portfolio(user_id, portfolio_id)
        transaction = await self._get_transaction_in_portfolio(portfolio_id, transaction_id)
        symbol = transaction.symbol
        await self._transactions.delete(transaction)
        await self._recompute_holding(portfolio_id, symbol)

    async def _recompute_holding(self, portfolio_id: UUID, symbol: str) -> None:
        """Replays all remaining transactions for a symbol to rebuild the holding's position."""
        remaining = await self._transactions.list_all_for_symbol(portfolio_id, symbol)
        state = PositionState()
        for txn in remaining:
            state = PositionEngine.apply(
                state,
                symbol=symbol,
                transaction_type=txn.transaction_type,
                quantity=float(txn.quantity),
                price=float(txn.price),
                fees=float(txn.fees),
                split_ratio_from=float(txn.split_ratio_from) if txn.split_ratio_from else None,
                split_ratio_to=float(txn.split_ratio_to) if txn.split_ratio_to else None,
            )
        holding = await self._holdings.get_by_symbol(portfolio_id, symbol)
        if holding is not None:
            await self._holdings.update(
                holding,
                quantity=Decimal(str(round(state.quantity, 6))),
                average_cost=Decimal(str(round(state.average_cost, 6))),
            )

    async def _get_owned_portfolio(self, user_id: UUID, portfolio_id: UUID) -> PortfolioModel:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        if portfolio.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return portfolio

    async def _get_transaction_in_portfolio(
        self, portfolio_id: UUID, transaction_id: UUID
    ) -> TransactionModel:
        transaction = await self._transactions.get_by_id(transaction_id)
        if transaction is None or transaction.portfolio_id != portfolio_id:
            raise TransactionNotFoundError(transaction_id)
        return transaction
