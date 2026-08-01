from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portfolio.domain.repositories import HoldingRepository
from app.modules.portfolio.infrastructure.models import HoldingModel

_SORTABLE_FIELDS = {
    "symbol": HoldingModel.symbol,
    "quantity": HoldingModel.quantity,
    "average_cost": HoldingModel.average_cost,
    "created_at": HoldingModel.created_at,
}


class SqlAlchemyHoldingRepository(HoldingRepository):
    """SQLAlchemy 2.0 (async) implementation of the Holding persistence port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> HoldingModel:
        entity = HoldingModel(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, holding_id: UUID) -> HoldingModel | None:
        return await self._session.get(HoldingModel, holding_id)

    async def get_by_symbol(self, portfolio_id: UUID, symbol: str) -> HoldingModel | None:
        stmt = select(HoldingModel).where(
            HoldingModel.portfolio_id == portfolio_id,
            HoldingModel.symbol == symbol.upper(),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_portfolio(
        self,
        portfolio_id: UUID,
        *,
        offset: int,
        limit: int,
        sector: str | None = None,
        sort_by: str = "symbol",
        sort_dir: str = "asc",
    ) -> list[HoldingModel]:
        stmt = select(HoldingModel).where(HoldingModel.portfolio_id == portfolio_id)
        if sector:
            stmt = stmt.where(HoldingModel.sector == sector)
        sort_column = _SORTABLE_FIELDS.get(sort_by, HoldingModel.symbol)
        stmt = stmt.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_for_portfolio(self, portfolio_id: UUID) -> list[HoldingModel]:
        stmt = select(HoldingModel).where(HoldingModel.portfolio_id == portfolio_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_portfolio(self, portfolio_id: UUID, *, sector: str | None = None) -> int:
        stmt = select(func.count(HoldingModel.id)).where(HoldingModel.portfolio_id == portfolio_id)
        if sector:
            stmt = stmt.where(HoldingModel.sector == sector)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, holding: HoldingModel, **kwargs) -> HoldingModel:
        for key, value in kwargs.items():
            if value is not None:
                setattr(holding, key, value)
        await self._session.flush()
        await self._session.refresh(holding)
        return holding

    async def delete(self, holding: HoldingModel) -> None:
        await self._session.delete(holding)
        await self._session.flush()
