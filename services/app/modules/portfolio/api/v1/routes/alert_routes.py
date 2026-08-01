from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import PageRequest, page_params
from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_alert_service
from app.modules.portfolio.application.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.modules.portfolio.application.schemas.common import MessageResponse, PaginatedResponse
from app.modules.portfolio.application.services.alert_service import AlertService
from app.modules.portfolio.domain.enums import AlertStatus, AlertType

router = APIRouter(prefix="/alerts", tags=["Watchlist Alerts"])


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
) -> AlertRead:
    """Create a TARGET_PRICE or STOP_LOSS alert for a symbol."""
    return await service.create_alert(current_user.id, payload)


@router.get("", response_model=PaginatedResponse[AlertRead])
async def list_alerts(
    page_request: PageRequest = Depends(page_params),
    status_filter: AlertStatus | None = Query(default=None, alias="status"),
    alert_type: AlertType | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
) -> PaginatedResponse[AlertRead]:
    """List the authenticated user's alerts, filterable by status/type."""
    return await service.list_alerts(
        current_user.id,
        offset=page_request.offset,
        limit=page_request.limit,
        page=page_request.page,
        page_size=page_request.page_size,
        status=status_filter.value if status_filter else None,
        alert_type=alert_type.value if alert_type else None,
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
) -> AlertRead:
    return await service.get_alert(current_user.id, alert_id)


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: UUID,
    payload: AlertUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
) -> AlertRead:
    return await service.update_alert(current_user.id, alert_id, payload)


@router.delete("/{alert_id}", response_model=MessageResponse)
async def delete_alert(
    alert_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
) -> MessageResponse:
    await service.delete_alert(current_user.id, alert_id)
    return MessageResponse(message="Alert deleted.")
