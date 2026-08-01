from __future__ import annotations

from typing import Protocol
from uuid import UUID


class AlertNotifier(Protocol):
    """
    Port for delivering a "your alert has triggered" notification.

    Kept intentionally minimal (no email/SMS/push specifics) so that
    infrastructure can implement it however is appropriate for the host
    application (e.g. publish to a Redis pub/sub channel that a notification
    worker consumes, push to a message queue, call an email provider, etc.).
    """

    async def notify_alert_triggered(
        self, *, user_id: UUID, symbol: str, alert_type: str, threshold_price: float, current_price: float
    ) -> None: ...
