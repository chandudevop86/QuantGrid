from __future__ import annotations

from uuid import UUID

from app.modules.portfolio.application.schemas.common import PaginatedResponse
from app.modules.portfolio.application.schemas.watchlist import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistRead,
    WatchlistUpdate,
)
from app.modules.portfolio.domain.exceptions import UnauthorizedPortfolioAccessError, WatchlistNotFoundError
from app.modules.portfolio.domain.repositories import WatchlistRepository
from app.modules.portfolio.infrastructure.models import WatchlistModel


class WatchlistService:
    """Use-case orchestration for Watchlist CRUD and item management."""

    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlists = watchlist_repository

    async def create_watchlist(self, user_id: UUID, payload: WatchlistCreate) -> WatchlistRead:
        watchlist = await self._watchlists.create(
            user_id=user_id, name=payload.name, description=payload.description
        )
        for item in payload.items:
            await self._watchlists.add_item(watchlist.id, item.symbol, item.notes)
        refreshed = await self._watchlists.get_by_id(watchlist.id)
        return WatchlistRead.model_validate(refreshed)

    async def get_watchlist(self, user_id: UUID, watchlist_id: UUID) -> WatchlistRead:
        watchlist = await self._get_owned_watchlist(user_id, watchlist_id)
        return WatchlistRead.model_validate(watchlist)

    async def list_watchlists(
        self, user_id: UUID, *, offset: int, limit: int, page: int, page_size: int
    ) -> PaginatedResponse[WatchlistRead]:
        watchlists = await self._watchlists.list_for_user(user_id, offset=offset, limit=limit)
        total = await self._watchlists.count_for_user(user_id)
        return PaginatedResponse.build(
            items=[WatchlistRead.model_validate(w) for w in watchlists],
            page=page,
            page_size=page_size,
            total_items=total,
        )

    async def update_watchlist(
        self, user_id: UUID, watchlist_id: UUID, payload: WatchlistUpdate
    ) -> WatchlistRead:
        watchlist = await self._get_owned_watchlist(user_id, watchlist_id)
        updated = await self._watchlists.update(
            watchlist, **payload.model_dump(exclude_unset=True, exclude_none=True)
        )
        return WatchlistRead.model_validate(updated)

    async def delete_watchlist(self, user_id: UUID, watchlist_id: UUID) -> None:
        watchlist = await self._get_owned_watchlist(user_id, watchlist_id)
        await self._watchlists.delete(watchlist)

    async def add_item(
        self, user_id: UUID, watchlist_id: UUID, payload: WatchlistItemCreate
    ) -> WatchlistRead:
        await self._get_owned_watchlist(user_id, watchlist_id)
        await self._watchlists.add_item(watchlist_id, payload.symbol, payload.notes)
        refreshed = await self._watchlists.get_by_id(watchlist_id)
        return WatchlistRead.model_validate(refreshed)

    async def remove_item(self, user_id: UUID, watchlist_id: UUID, symbol: str) -> WatchlistRead:
        await self._get_owned_watchlist(user_id, watchlist_id)
        await self._watchlists.remove_item(watchlist_id, symbol)
        refreshed = await self._watchlists.get_by_id(watchlist_id)
        return WatchlistRead.model_validate(refreshed)

    async def _get_owned_watchlist(self, user_id: UUID, watchlist_id: UUID) -> WatchlistModel:
        watchlist = await self._watchlists.get_by_id(watchlist_id)
        if watchlist is None:
            raise WatchlistNotFoundError(watchlist_id)
        if watchlist.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return watchlist
