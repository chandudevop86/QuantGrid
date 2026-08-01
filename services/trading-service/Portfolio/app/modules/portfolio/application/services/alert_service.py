from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.modules.portfolio.application.interfaces.notifier import AlertNotifier
from app.modules.portfolio.application.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.modules.portfolio.application.schemas.common import PaginatedResponse
from app.modules.portfolio.domain.enums import AlertDirection, AlertStatus
from app.modules.portfolio.domain.exceptions import AlertNotFoundError, UnauthorizedPortfolioAccessError
from app.modules.portfolio.domain.repositories import AlertRepository
from app.modules.portfolio.infrastructure.models import AlertModel


class AlertService:
    """Use-case orchestration for target-price / stop-loss alert CRUD and evaluation."""

    def __init__(self, alert_repository: AlertRepository, notifier: AlertNotifier) -> None:
        self._alerts = alert_repository
        self._notifier = notifier

    async def create_alert(self, user_id: UUID, payload: AlertCreate) -> AlertRead:
        alert = await self._alerts.create(
            user_id=user_id,
            portfolio_id=payload.portfolio_id,
            symbol=payload.symbol,
            alert_type=payload.alert_type,
            direction=payload.direction,
            threshold_price=payload.threshold_price,
            notes=payload.notes,
        )
        return AlertRead.model_validate(alert)

    async def get_alert(self, user_id: UUID, alert_id: UUID) -> AlertRead:
        alert = await self._get_owned_alert(user_id, alert_id)
        return AlertRead.model_validate(alert)

    async def list_alerts(
        self,
        user_id: UUID,
        *,
        offset: int,
        limit: int,
        page: int,
        page_size: int,
        status: str | None = None,
        alert_type: str | None = None,
    ) -> PaginatedResponse[AlertRead]:
        alerts = await self._alerts.list_for_user(
            user_id, offset=offset, limit=limit, status=status, alert_type=alert_type
        )
        total = await self._alerts.count_for_user(user_id, status=status, alert_type=alert_type)
        return PaginatedResponse.build(
            items=[AlertRead.model_validate(a) for a in alerts],
            page=page,
            page_size=page_size,
            total_items=total,
        )

    async def update_alert(self, user_id: UUID, alert_id: UUID, payload: AlertUpdate) -> AlertRead:
        alert = await self._get_owned_alert(user_id, alert_id)
        updated = await self._alerts.update(alert, **payload.model_dump(exclude_unset=True, exclude_none=True))
        return AlertRead.model_validate(updated)

    async def delete_alert(self, user_id: UUID, alert_id: UUID) -> None:
        alert = await self._get_owned_alert(user_id, alert_id)
        await self._alerts.delete(alert)

    async def evaluate_price_update(self, symbol: str, current_price: float) -> list[AlertRead]:
        """
        Checks all ACTIVE alerts for `symbol` against `current_price`, marking
        and notifying any that have been triggered. Intended to be invoked by a
        market-data ingestion pipeline / scheduled job as new quotes arrive.
        """
        candidates = await self._alerts.list_active_for_symbol(symbol)
        triggered: list[AlertModel] = []
        for alert in candidates:
            threshold = float(alert.threshold_price)
            is_triggered = (
                current_price >= threshold
                if alert.direction == AlertDirection.ABOVE
                else current_price <= threshold
            )
            if is_triggered:
                await self._alerts.update(
                    alert,
                    status=AlertStatus.TRIGGERED,
                    triggered_at=datetime.now(timezone.utc),
                )
                await self._notifier.notify_alert_triggered(
                    user_id=alert.user_id,
                    symbol=alert.symbol,
                    alert_type=alert.alert_type.value if hasattr(alert.alert_type, "value") else alert.alert_type,
                    threshold_price=threshold,
                    current_price=current_price,
                )
                triggered.append(alert)
        return [AlertRead.model_validate(a) for a in triggered]

    async def _get_owned_alert(self, user_id: UUID, alert_id: UUID) -> AlertModel:
        alert = await self._alerts.get_by_id(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        if alert.user_id != user_id:
            raise UnauthorizedPortfolioAccessError()
        return alert
