from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import PageRequest, page_params
from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_transaction_service
from app.modules.portfolio.application.schemas.common import MessageResponse, PaginatedResponse
from app.modules.portfolio.application.schemas.transaction import TransactionCreate, TransactionRead
from app.modules.portfolio.application.services.transaction_service import TransactionService
from app.modules.portfolio.domain.enums import TransactionType

router = APIRouter(prefix="/portfolios/{portfolio_id}/transactions", tags=["Transactions"])


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def record_transaction(
    portfolio_id: UUID,
    payload: TransactionCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: TransactionService = Depends(get_transaction_service),
) -> TransactionRead:
    """Record a BUY, SELL, DIVIDEND, BONUS, or SPLIT transaction. Updates the holding position."""
    return await service.record_transaction(current_user.id, portfolio_id, payload)


@router.get("", response_model=PaginatedResponse[TransactionRead])
async def list_transactions(
    portfolio_id: UUID,
    page_request: PageRequest = Depends(page_params),
    symbol: str | None = Query(default=None),
    transaction_type: TransactionType | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    sort_by: str = Query(default="transaction_date", pattern="^(transaction_date|created_at|symbol|quantity|price)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: CurrentUser = Depends(get_current_user),
    service: TransactionService = Depends(get_transaction_service),
) -> PaginatedResponse[TransactionRead]:
    return await service.list_transactions(
        current_user.id,
        portfolio_id,
        offset=page_request.offset,
        limit=page_request.limit,
        page=page_request.page,
        page_size=page_request.page_size,
        symbol=symbol,
        transaction_type=transaction_type.value if transaction_type else None,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TransactionService = Depends(get_transaction_service),
) -> TransactionRead:
    return await service.get_transaction(current_user.id, portfolio_id, transaction_id)


@router.delete("/{transaction_id}", response_model=MessageResponse)
async def delete_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TransactionService = Depends(get_transaction_service),
) -> MessageResponse:
    """Delete a transaction and recompute the affected holding's position from history."""
    await service.delete_transaction(current_user.id, portfolio_id, transaction_id)
    return MessageResponse(message="Transaction deleted and holding position recomputed.")
