from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError


YAHOO_TRADING_GRADE_WARNING = "Yahoo data is not trading-grade and should not be used for live execution."
YAHOO_SYMBOLS = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
}


class YahooProvider(MarketDataProvider):
    provider_name = "yahoo"
    live_suitable = False
    paper_suitable = True
    warning = YAHOO_TRADING_GRADE_WARNING
    retries = 2

    def normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.upper().replace(" ", "").replace("-", "_")
        return YAHOO_SYMBOLS.get(normalized, symbol.upper())

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        self.mark_fetch()
        yahoo_symbol = self.normalize_symbol(symbol)
        params = urlencode({"range": period, "interval": interval, "includePrePost": "false"})
        request = Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(yahoo_symbol, safe='')}?{params}",
            headers={"User-Agent": "QuantGrid/1.0"},
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                started = time.monotonic()
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                result = payload.get("chart", {}).get("result") or []
                if not result:
                    raise MarketDataProviderError(str(payload.get("chart", {}).get("error") or "No market data returned"))
                result[0]["provider_latency_ms"] = round((time.monotonic() - started) * 1000)
                return result[0]
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
        raise MarketDataProviderError(str(last_error or "Yahoo market data fetch failed"))

    def get_ltp(self, symbol: str) -> dict[str, Any]:
        chart = self.fetch_chart(symbol, interval="1m", period="1d")
        meta = chart.get("meta", {})
        price = meta.get("regularMarketPrice")
        return {
            "provider": self.provider_name,
            "symbol": symbol.upper(),
            "market_symbol": meta.get("symbol", self.normalize_symbol(symbol)),
            "exchange": "NSE",
            "ltp": round(float(price), 2) if price not in {None, ""} else None,
            "price": round(float(price), 2) if price not in {None, ""} else None,
            "timestamp": self.latest_fetch_at,
            "source": "demo",
            "exchange_timezone": meta.get("timezone"),
            "provider_latency_ms": chart.get("provider_latency_ms"),
            "provider_warning": self.warning,
        }

    def get_candles(self, symbol: str, interval: str, period: str, limit: int) -> list[dict[str, Any]]:
        chart = self.fetch_chart(symbol, interval=interval, period=period)
        timestamps = chart.get("timestamp") or []
        quote_data = (chart.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote_data.get("open") or []
        highs = quote_data.get("high") or []
        lows = quote_data.get("low") or []
        closes = quote_data.get("close") or []
        volumes = quote_data.get("volume") or []
        timezone_name = chart.get("meta", {}).get("timezone", "Asia/Kolkata")
        candles: list[dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps):
            values = [
                opens[index] if index < len(opens) else None,
                highs[index] if index < len(highs) else None,
                lows[index] if index < len(lows) else None,
                closes[index] if index < len(closes) else None,
            ]
            if any(value is None for value in values):
                continue
            candles.append(
                {
                    "symbol": symbol.upper(),
                    "timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    "exchange_timezone": timezone_name,
                    "open": round(float(values[0]), 2),
                    "high": round(float(values[1]), 2),
                    "low": round(float(values[2]), 2),
                    "close": round(float(values[3]), 2),
                    "volume": int(volumes[index] or 0) if index < len(volumes) else 0,
                }
            )
        return candles[-max(1, min(int(limit), 500)):]

    def subscribe_ticks(self, symbols: Iterable[str]) -> None:
        raise MarketDataProviderError("Yahoo does not provide a trading-grade live tick websocket.")

    def health_check(self) -> dict[str, Any]:
        return self.status_payload() | {
            "configured": True,
            "connected": False,
            "healthy": True,
            "message": "Yahoo demo market data is available for paper/demo mode only.",
        }
