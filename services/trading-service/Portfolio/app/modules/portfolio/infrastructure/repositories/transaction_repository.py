from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portfolio.domain.repositories import TransactionRepository
from app.modules.portfolio.infrastructure.models import TransactionModel

_SORTABLE_FIELDS = {
    "transaction_date": TransactionModel.transaction_date,
    "created_at": TransactionModel.created_at,
    "symbol": TransactionModel.symbol,
    "quantity": TransactionModel.quantity,
    "price": TransactionModel.price,
}


class SqlAlchemyTransactionRepository(TransactionRepository):
    """SQLAlchemy 2.0 (async) implementation of the Transaction persistence port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> TransactionModel:
        entity = TransactionModel(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, transaction_id: UUID) -> TransactionModel | None:
        return await self._session.get(TransactionModel, transaction_id)

    def _filtered_stmt(
        self,
        portfolio_id: UUID,
        *,
        symbol: str | None = None,
        transaction_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        stmt = select(TransactionModel).where(TransactionModel.portfolio_id == portfolio_id)
        if symbol:
            stmt = stmt.where(TransactionModel.symbol == symbol.upper())
        if transaction_type:
            stmt = stmt.where(TransactionModel.transaction_type == transaction_type)
        if start_date:
            stmt = stmt.where(TransactionModel.transaction_date >= start_date)
        if end_date:
            stmt = stmt.where(TransactionModel.transaction_date <= end_date)
        return stmt

    async def list_for_portfolio(
        self,
        portfolio_id: UUID,
        *,
        offset: int,
        limit: int,
        symbol: str | None = None,
        transaction_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        sort_by: str = "transaction_date",
        sort_dir: str = "desc",
    ) -> list[TransactionModel]:
        stmt = self._filtered_stmt(
            portfolio_id,
            symbol=symbol,
            transaction_type=transaction_type,
            start_date=start_date,
            end_date=end_date,
        )
        sort_column = _SORTABLE_FIELDS.get(sort_by, TransactionModel.transaction_date)
        stmt = stmt.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_portfolio(self, portfolio_id: UUID, **filters) -> int:
        stmt = self._filtered_stmt(portfolio_id, **filters)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self._session.execute(count_stmt)
        return int(result.scalar_one())

    async def list_all_for_symbol(self, portfolio_id: UUID, symbol: str) -> list[TransactionModel]:
        stmt = (
            select(TransactionModel)
            .where(
                TransactionModel.portfolio_id == portfolio_id,
                TransactionModel.symbol == symbol.upper(),
            )
            .order_by(TransactionModel.transaction_date.asc(), TransactionModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_for_portfolio(self, portfolio_id: UUID) -> list[TransactionModel]:
        stmt = (
            select(TransactionModel)
            .where(TransactionModel.portfolio_id == portfolio_id)
            .order_by(TransactionModel.transaction_date.asc(), TransactionModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, transaction: TransactionModel) -> None:
        await self._session.delete(transaction)
        await self._session.flush()
