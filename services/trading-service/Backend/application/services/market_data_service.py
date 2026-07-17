from __future__ import annotations

import logging
from typing import Any

from Backend.application.market_data_service import MarketDataService as BaseMarketDataService

logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(self) -> None:
        self.service = BaseMarketDataService()

    def get_candles(
        self,
        symbol: str,
        interval: str,
        period: str,
        limit: int,
    ) -> dict[str, Any]:

        response = self.service.get_candles(
            symbol=symbol,
            interval=interval,
            period=period,
            limit=limit,
        )

        candles = response.get("candles", [])

        if len(candles) == 0:
            raise RuntimeError(
                f"No candles returned for {symbol}"
            )

        return response