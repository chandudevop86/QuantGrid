from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from Backend.domain.market_data.provider import MarketDataProviderError
from Backend.infrastructure.market_data.base import EnvConfiguredProvider
from Backend.infrastructure.market_data.dhan_sdk import dhan_market_feed_class, dhan_sdk_client


SECURITY_MASTER = None

INDEX_SPOT_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY"}

# Set up module logger instance for tracking resolution failures
logger = logging.getLogger(__name__)
def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return default


def _safe_index(values: list[Any], index: int) -> Any:
        
        return values[index] if index < len(values) else None

class DhanProvider(EnvConfiguredProvider):
    provider_name = "dhan"
    required_env = ("QUANTGRID_BROKER_CLIENT_ID", "QUANTGRID_BROKER_ACCESS_TOKEN")
    def normalize_symbol(self, symbol: str) -> str:
        return symbol.upper()

    def resolve_instrument(
        self,
        symbol: str,
        expiry: str | None = None,
        strike: float | None = None,
        option_type: str | None = None,
    ) -> dict[str, Any]:
        # Option/Future instrument
        if (
            expiry is not None
            and strike is not None
            and option_type is not None
        ):
            if SECURITY_MASTER is None:
                raise MarketDataProviderError("Security Master CSV is not installed.")

            return SECURITY_MASTER.resolve(
                symbol=symbol,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
            )

        # Cash / Index instrument
        security_id = os.getenv(f"DHAN_SECURITY_ID_{symbol.upper()}")

        if security_id:
            return {
                "security_id": security_id,
                "exchange_segment": _exchange_segment(),
                "symbol": symbol.upper(),
            }

        # Fallback to Security Master
        if SECURITY_MASTER is not None:
            try:
                instrument = SECURITY_MASTER.resolve(symbol=symbol)
                return instrument
            except Exception as exc:
                logger.debug(
                    "Unable to resolve instrument: %s",
                    exc,
                )
                pass

        raise MarketDataProviderError(
            f"Unable to resolve Dhan Security ID for '{symbol}'. "
            f"Configure DHAN_SECURITY_ID_{symbol.upper()} or ensure "
            f"data/dhan_security_master.csv contains the instrument."
        )

    def get_ltp(self, symbol: str) -> dict[str, Any]:
        self._require_configured()

        normalized = symbol.upper()

        # Dhan marketfeed REST doesn't return spot index quotes; fall back to Yahoo
        if normalized in INDEX_SPOT_SYMBOLS:
            from Backend.infrastructure.market_data.yahoo_provider import YahooProvider
            return YahooProvider().get_ltp(normalized)

        dhan = dhan_sdk_client()
        instrument = self.resolve_instrument(symbol)
        security_id = instrument["security_id"]
        exchange_segment = instrument["exchange_segment"]
        security = int(security_id) if str(security_id).isdigit() else security_id
        
        raw = dhan.ohlc_data(securities={exchange_segment: [security]})
        logger.debug("Raw Dhan response: %r", raw)
        
        quote = _extract_quote(raw, security_id)
        
        logger.debug("Extracted quote: %r", quote)
        
        print("EXTRACTED QUOTE:", quote)
        
        ltp = (
            quote.get("last_price")
            or quote.get("ltp")
            or quote.get("lastPrice")
            or quote.get("LTP")
        )
        
        if ltp in (None, ""):
            raise MarketDataProviderError("Dhan quote response did not contain LTP.")
            
        fetched_at = self.mark_fetch()
        return {
            "provider": self.provider_name,
            "symbol": symbol.upper(),
            "security_id": security_id,
            "exchange_segment": exchange_segment,       
            "market_symbol": security_id,
            "exchange": "NSE",
            "ltp": _to_float(ltp),
            "price": _to_float(ltp),
            "timestamp": fetched_at,
            "source": "live",
            "exchange_timezone": "Asia/Kolkata",
            "raw_safe": _safe_raw(raw),
        }

    def get_candles(self, symbol: str, interval: str, period: str, limit: int) -> list[dict[str, Any]]:
        self._require_configured()
        dhan = dhan_sdk_client()
        instrument = self.resolve_instrument(symbol)
        security_id = instrument["security_id"]
        security = int(security_id) if str(security_id).isdigit() else security_id
        exchange_segment = instrument["exchange_segment"]
        
        to_date = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        from_date = to_date - timedelta(days=max(1, _period_days(period)))
        
        raw = dhan.intraday_minute_data(
            security_id=str(security),
            exchange_segment=exchange_segment,
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
        instruments = []

        for symbol in symbols:
            instrument = self.resolve_instrument(symbol)
            if not instrument.get("security_id"):
                continue

            instruments.append(
                (
                    instrument["exchange_segment"],
                    str(instrument["security_id"]),
                    market_feed.Ticker,
                )
            )

        feed = market_feed(context, instruments, "v2")
        feed.run_forever()


# --- Helper Functions (Outside Class Block) ---

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
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
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
        return data
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
                    "open": _to_float(_safe_index(opens, index)),
                    "high": _to_float(_safe_index(highs, index)),
                    "low": _to_float(_safe_index(lows, index)),
                    "close": _to_float(_safe_index(closes, index)),
                    "volume": int(_safe_index(volumes, index) or 0),
                }
            )
        return rows
        
    if isinstance(data, list):
        return [
            {
                "symbol": symbol.upper(),
                "timestamp": _timestamp_to_ist(item.get("timestamp") or item.get("time") or item.get("start_Time")),
                "exchange_timezone": "Asia/Kolkata",
                "open": _to_float(item.get("open")),
                "high": _to_float(item.get("high")),
                "low": _to_float(item.get("low")),
                "close": _to_float(item.get("close")),
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
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if "token" not in k.lower() and "secret" not in k.lower()}
    return value
