from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from Backend.domain.market_data.provider import MarketDataProviderError
from Backend.infrastructure.market_data.base import EnvConfiguredProvider
from Backend.infrastructure.market_data.dhan_sdk import dhan_market_feed_class, dhan_sdk_client


class DhanProvider(EnvConfiguredProvider):
    provider_name = "dhan"
    required_env = ("QUANTGRID_BROKER_CLIENT_ID", "QUANTGRID_BROKER_ACCESS_TOKEN")

    def normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.upper().replace(" ", "").replace("-", "_")
        return os.getenv(f"DHAN_SECURITY_ID_{normalized}", "13" if normalized in {"NIFTY", "NIFTY50", "NIFTY_50"} else normalized)

    def get_ltp(self, symbol: str) -> dict[str, Any]:
        self._require_configured()
        dhan = dhan_sdk_client()
        security_id = self.normalize_symbol(symbol)
        raw = dhan.ohlc_data(securities={_exchange_segment(): [int(security_id) if str(security_id).isdigit() else security_id]})
        quote = _extract_quote(raw, security_id)
        ltp = quote.get("last_price") or quote.get("ltp") or quote.get("lastPrice") or quote.get("LTP")
        if ltp in {None, ""}:
            raise MarketDataProviderError("Dhan quote response did not contain LTP.")
        fetched_at = self.mark_fetch()
        return {
            "provider": self.provider_name,
            "symbol": symbol.upper(),
            "market_symbol": security_id,
            "exchange": "NSE",
            "ltp": float(ltp),
            "price": float(ltp),
            "timestamp": fetched_at,
            "source": "live",
            "exchange_timezone": "Asia/Kolkata",
            "raw_safe": _safe_raw(raw),
        }

    def get_candles(self, symbol: str, interval: str, period: str, limit: int) -> list[dict[str, Any]]:
        self._require_configured()
        dhan = dhan_sdk_client()
        security_id = self.normalize_symbol(symbol)
        to_date = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        from_date = to_date - timedelta(days=max(1, _period_days(period)))
        raw = dhan.intraday_minute_data(
            security_id=str(security_id),
            exchange_segment=_exchange_segment(),
            instrument_type=os.getenv("DHAN_INSTRUMENT_TYPE", "INDEX"),
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
        )
        self.mark_fetch()
        candles = _normalize_candles(symbol, raw)
        return candles[-max(1, min(int(limit), 500)):]

    def subscribe_ticks(self, symbols: Iterable[str]) -> None:
        self._require_configured()
        context, market_feed = dhan_market_feed_class()
        instruments = [
            (market_feed.NSE, str(self.normalize_symbol(symbol)), market_feed.Ticker)
            for symbol in symbols
        ]
        feed = market_feed(context, instruments, "v2")
        feed.run_forever()


def _exchange_segment() -> str:
    return os.getenv("DHAN_MARKET_EXCHANGE_SEGMENT", "IDX_I")


def _period_days(period: str) -> int:
    value = str(period or "1d").lower()
    if value.endswith("d"):
        try:
            return int(value[:-1])
        except ValueError:
            return 1
    return 1


def _extract_quote(raw: Any, security_id: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        data = raw.get("data", raw)
        if isinstance(data, dict):
            for key in (security_id, str(security_id), "NSE", "IDX_I"):
                item = data.get(key)
                if isinstance(item, dict):
                    return item
            for item in data.values():
                if isinstance(item, dict):
                    nested = _extract_quote(item, security_id)
                    if nested:
                        return nested
        return data if isinstance(data, dict) else {}
    return {}


def _normalize_candles(symbol: str, raw: Any) -> list[dict[str, Any]]:
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    if isinstance(data, dict):
        timestamps = data.get("timestamp") or data.get("time") or data.get("start_Time") or []
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        volumes = data.get("volume") or []
        rows = []
        for index, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "symbol": symbol.upper(),
                    "timestamp": _timestamp_to_ist(timestamp),
                    "exchange_timezone": "Asia/Kolkata",
                    "open": float(opens[index]),
                    "high": float(highs[index]),
                    "low": float(lows[index]),
                    "close": float(closes[index]),
                    "volume": int(volumes[index] or 0) if index < len(volumes) else 0,
                }
            )
        return rows
    if isinstance(data, list):
        return [
            {
                "symbol": symbol.upper(),
                "timestamp": _timestamp_to_ist(item.get("timestamp") or item.get("time") or item.get("start_Time")),
                "exchange_timezone": "Asia/Kolkata",
                "open": float(item.get("open")),
                "high": float(item.get("high")),
                "low": float(item.get("low")),
                "close": float(item.get("close")),
                "volume": int(item.get("volume") or 0),
            }
            for item in data
            if isinstance(item, dict) and item.get("close") is not None
        ]
    return []


def _timestamp_to_ist(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), ZoneInfo("Asia/Kolkata")).isoformat()
    timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    return timestamp.astimezone(ZoneInfo("Asia/Kolkata")).isoformat()


def _safe_raw(value: Any) -> Any:
    secret_keys = {"access-token", "access_token", "token", "authorization", "clientSecret", "apiSecret"}
    if isinstance(value, dict):
        return {key: ("[redacted]" if str(key).lower() in {item.lower() for item in secret_keys} else _safe_raw(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_raw(item) for item in value]
    return value
