from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portfolio.domain.repositories import PortfolioRepository
from app.modules.portfolio.infrastructure.models import PortfolioModel

_SORTABLE_FIELDS = {
    "name": PortfolioModel.name,
    "created_at": PortfolioModel.created_at,
    "updated_at": PortfolioModel.updated_at,
}


class SqlAlchemyPortfolioRepository(PortfolioRepository):
    """SQLAlchemy 2.0 (async) implementation of the Portfolio persistence port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> PortfolioModel:
        entity = PortfolioModel(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, portfolio_id: UUID) -> PortfolioModel | None:
        return await self._session.get(PortfolioModel, portfolio_id)

    async def get_by_name_for_user(self, user_id: UUID, name: str) -> PortfolioModel | None:
        stmt = select(PortfolioModel).where(
            PortfolioModel.user_id == user_id, PortfolioModel.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        offset: int,
        limit: int,
        portfolio_type: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        include_archived: bool = False,
    ) -> list[PortfolioModel]:
        stmt = select(PortfolioModel).where(PortfolioModel.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(PortfolioModel.is_archived.is_(False))
        if portfolio_type:
            stmt = stmt.where(PortfolioModel.portfolio_type == portfolio_type)

        sort_column = _SORTABLE_FIELDS.get(sort_by, PortfolioModel.created_at)
        stmt = stmt.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(
        self,
        user_id: UUID,
        *,
        portfolio_type: str | None = None,
        include_archived: bool = False,
    ) -> int:
        stmt = select(func.count(PortfolioModel.id)).where(PortfolioModel.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(PortfolioModel.is_archived.is_(False))
        if portfolio_type:
            stmt = stmt.where(PortfolioModel.portfolio_type == portfolio_type)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, portfolio: PortfolioModel, **kwargs) -> PortfolioModel:
        for key, value in kwargs.items():
            if value is not None:
                setattr(portfolio, key, value)
        await self._session.flush()
        await self._session.refresh(portfolio)
        return portfolio

    async def delete(self, portfolio: PortfolioModel) -> None:
        await self._session.delete(portfolio)
        await self._session.flush()
