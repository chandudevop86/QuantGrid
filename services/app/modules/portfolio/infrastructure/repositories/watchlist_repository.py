from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.portfolio.domain.repositories import WatchlistRepository
from app.modules.portfolio.infrastructure.models import WatchlistItemModel, WatchlistModel


class SqlAlchemyWatchlistRepository(WatchlistRepository):
    """SQLAlchemy 2.0 (async) implementation of the Watchlist persistence port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> WatchlistModel:
        entity = WatchlistModel(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        # Refresh scalar columns only (id/timestamps); deliberately leave the
        # `items` relationship unloaded so a subsequent `get_by_id` (which
        # eager-loads it via selectinload) fetches it fresh rather than
        # reusing an empty collection cached from before items were added.
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, watchlist_id: UUID) -> WatchlistModel | None:
        stmt = (
            select(WatchlistModel)
            .where(WatchlistModel.id == watchlist_id)
            .options(selectinload(WatchlistModel.items))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID, *, offset: int, limit: int) -> list[WatchlistModel]:
        stmt = (
            select(WatchlistModel)
            .where(WatchlistModel.user_id == user_id)
            .options(selectinload(WatchlistModel.items))
            .order_by(WatchlistModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        stmt = select(func.count(WatchlistModel.id)).where(WatchlistModel.user_id == user_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def update(self, watchlist: WatchlistModel, **kwargs) -> WatchlistModel:
        for key, value in kwargs.items():
            if value is not None:
                setattr(watchlist, key, value)
        await self._session.flush()
        await self._session.refresh(watchlist)
        return watchlist

    async def delete(self, watchlist: WatchlistModel) -> None:
        await self._session.delete(watchlist)
        await self._session.flush()

    async def add_item(
        self, watchlist_id: UUID, symbol: str, notes: str | None = None
    ) -> WatchlistItemModel:
        item = WatchlistItemModel(watchlist_id=watchlist_id, symbol=symbol.upper(), notes=notes)
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def get_item(self, watchlist_id: UUID, symbol: str) -> WatchlistItemModel | None:
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.watchlist_id == watchlist_id,
            WatchlistItemModel.symbol == symbol.upper(),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def remove_item(self, watchlist_id: UUID, symbol: str) -> None:
        item = await self.get_item(watchlist_id, symbol)
        if item is not None:
            await self._session.delete(item)
            await self._session.flush()
