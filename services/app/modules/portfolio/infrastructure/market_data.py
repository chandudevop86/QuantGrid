from __future__ import annotations

import json
from datetime import date, datetime

import redis.asyncio as redis

from app.modules.portfolio.domain.exceptions import InsufficientDataError

_PRICE_KEY = "quantgrid:market:price:{symbol}"
_HISTORY_KEY = "quantgrid:market:history:{symbol}"
_META_KEY = "quantgrid:market:meta:{symbol}"


class RedisMarketDataProvider:
    """
    Adapter implementing the `MarketDataProvider` port on top of Redis.

    Design: this module owns *portfolio* concerns, not market-data ingestion.
    A separate market-data pipeline (out of scope for this module) is expected
    to populate Redis with the keys read here:

      - `quantgrid:market:price:{symbol}`            -> string, latest close price
      - `quantgrid:market:history:{symbol}`           -> hash of {"YYYY-MM-DD": price}
      - `quantgrid:market:meta:{symbol}`              -> JSON {"sector", "asset_class",
                                                          "market_cap_segment", "beta", "name"}

    Keeping this as a thin adapter means the vendor integration (e.g. a
    scheduled job hitting a quotes API) can be swapped freely without
    touching any domain or application code, since callers only depend on
    the `MarketDataProvider` Protocol.
    """

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def get_latest_price(self, symbol: str) -> float:
        raw = await self._client.get(_PRICE_KEY.format(symbol=symbol.upper()))
        if raw is None:
            raise InsufficientDataError(f"No cached market price available for '{symbol}'.")
        return float(raw)

    async def get_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[tuple[date, float]]:
        raw = await self._client.hgetall(_HISTORY_KEY.format(symbol=symbol.upper()))
        if not raw:
            raise InsufficientDataError(f"No cached price history available for '{symbol}'.")
        points: list[tuple[date, float]] = []
        for day_str, price_str in raw.items():
            try:
                day = datetime.strptime(day_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if start_date <= day <= end_date:
                points.append((day, float(price_str)))
        return sorted(points, key=lambda p: p[0])

    async def get_security_metadata(self, symbol: str) -> dict:
        raw = await self._client.get(_META_KEY.format(symbol=symbol.upper()))
        if raw is None:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
