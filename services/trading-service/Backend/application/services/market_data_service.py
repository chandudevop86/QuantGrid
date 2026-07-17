from __future__ import annotations

import logging

from Backend.presentation.api.market_api import get_candles

logger = logging.getLogger(__name__)


class MarketDataService:

    def get_candles(
        self,
        symbol: str,
        interval: str,
        period: str,
        limit: int,
    ):

        response = get_candles(
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