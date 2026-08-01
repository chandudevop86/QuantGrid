from __future__ import annotations

import json
from uuid import UUID

import redis.asyncio as redis

ALERT_TRIGGERED_CHANNEL = "quantgrid:alerts:triggered"


class RedisAlertNotifier:
    """Publishes triggered-alert events to a Redis pub/sub channel for downstream consumers."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def notify_alert_triggered(
        self, *, user_id: UUID, symbol: str, alert_type: str, threshold_price: float, current_price: float
    ) -> None:
        payload = json.dumps(
            {
                "user_id": str(user_id),
                "symbol": symbol,
                "alert_type": alert_type,
                "threshold_price": threshold_price,
                "current_price": current_price,
            }
        )
        await self._client.publish(ALERT_TRIGGERED_CHANNEL, payload)
