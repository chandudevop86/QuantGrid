from __future__ import annotations

import logging
from typing import Any

from Backend.domain.market_data.provider import MarketDataProvider


logger = logging.getLogger(__name__)


class MarketDataService:

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider


    def get_candles(
        self,
        symbol: str,
        interval: str,
        period: str = "1d",
        limit: int = 100,
        *,
        mode: str = "paper",
    ) -> dict[str, Any]:

        candles = self.provider.get_candles(
            symbol=symbol,
            interval=interval,
            period=period,
            limit=limit,
        )

        if not candles:
            raise RuntimeError(
                f"No candles returned for {symbol}"
            )

        return {
            "symbol": symbol,
            "interval": interval,
            "period": period,
            "candles": candles,
        }