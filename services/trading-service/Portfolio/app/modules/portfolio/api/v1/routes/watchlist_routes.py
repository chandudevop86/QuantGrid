from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.pagination import PageRequest, page_params
from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_watchlist_service
from app.modules.portfolio.application.schemas.common import MessageResponse, PaginatedResponse
from app.modules.portfolio.application.schemas.watchlist import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistRead,
    WatchlistUpdate,
)
from app.modules.portfolio.application.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/watchlists", tags=["Watchlists"])


@router.post("", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    payload: WatchlistCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    return await service.create_watchlist(current_user.id, payload)


@router.get("", response_model=PaginatedResponse[WatchlistRead])
async def list_watchlists(
    page_request: PageRequest = Depends(page_params),
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> PaginatedResponse[WatchlistRead]:
    return await service.list_watchlists(
        current_user.id,
        offset=page_request.offset,
        limit=page_request.limit,
        page=page_request.page,
        page_size=page_request.page_size,
    )


@router.get("/{watchlist_id}", response_model=WatchlistRead)
async def get_watchlist(
    watchlist_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    return await service.get_watchlist(current_user.id, watchlist_id)


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
async def update_watchlist(
    watchlist_id: UUID,
    payload: WatchlistUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    return await service.update_watchlist(current_user.id, watchlist_id, payload)


@router.delete("/{watchlist_id}", response_model=MessageResponse)
async def delete_watchlist(
    watchlist_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> MessageResponse:
    await service.delete_watchlist(current_user.id, watchlist_id)
    return MessageResponse(message="Watchlist deleted.")


@router.post("/{watchlist_id}/items", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(
    watchlist_id: UUID,
    payload: WatchlistItemCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    return await service.add_item(current_user.id, watchlist_id, payload)


@router.delete("/{watchlist_id}/items/{symbol}", response_model=WatchlistRead)
async def remove_watchlist_item(
    watchlist_id: UUID,
    symbol: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    return await service.remove_item(current_user.id, watchlist_id, symbol)
