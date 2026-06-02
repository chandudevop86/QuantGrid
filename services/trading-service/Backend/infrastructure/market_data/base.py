from __future__ import annotations

import os
from typing import Any, Iterable

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError


NSE_SYMBOLS = {
    "NIFTY": "NSE:NIFTY 50",
    "NIFTY50": "NSE:NIFTY 50",
    "NIFTY_50": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "NIFTYBANK": "NSE:NIFTY BANK",
}


class EnvConfiguredProvider(MarketDataProvider):
    live_suitable = True
    paper_suitable = True
    required_env: tuple[str, ...] = ()

    def normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.upper().replace("-", "_").replace(" ", "")
        return NSE_SYMBOLS.get(normalized, symbol.upper())

    def health_check(self) -> dict[str, Any]:
        missing = [key for key in self.required_env if not os.getenv(key)]
        return self.status_payload() | {
            "configured": not missing,
            "connected": False,
            "healthy": not missing,
            "missing_config": missing,
            "message": "Provider credentials configured." if not missing else f"Missing provider env: {', '.join(missing)}",
        }

    def _require_configured(self) -> None:
        status = self.health_check()
        if not status["configured"]:
            raise MarketDataProviderError(status["message"])

    def get_ltp(self, symbol: str) -> dict[str, Any]:
        self._require_configured()
        raise MarketDataProviderError(f"{self.provider_name} live LTP adapter is not configured yet.")

    def get_candles(self, symbol: str, interval: str, period: str, limit: int) -> list[dict[str, Any]]:
        self._require_configured()
        raise MarketDataProviderError(f"{self.provider_name} live candle adapter is not configured yet.")

    def subscribe_ticks(self, symbols: Iterable[str]) -> None:
        self._require_configured()
        raise MarketDataProviderError(f"{self.provider_name} tick websocket adapter is not configured yet.")
