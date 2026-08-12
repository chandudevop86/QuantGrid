from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from Backend.domain.market_data.provider import MarketDataProviderError
from Backend.infrastructure.market_data.base import EnvConfiguredProvider
from Backend.infrastructure.market_data.dhan_sdk import dhan_market_feed_class, dhan_sdk_client
from Backend.config import Provider
from datetime import datetime, time
from zoneinfo import ZoneInfo

SECURITY_MASTER = None

INDEX_SPOT_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY"}

# Set up module logger instance for tracking resolution failures
logger = logging.getLogger(__name__)
def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return default


from typing import Any

def _safe_index(values: list[Any], index: int) -> float | None:
    if index >= len(values):
        return None

    value = values[index]

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
class DhanProvider(EnvConfiguredProvider):
    provider_name = "dhan"
    provider = Provider.DHAN
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
        normalized_symbol = str(symbol).strip().upper()

        print(
            "DHAN DEBUG:",
            {
                "raw_symbol": repr(symbol),
                "normalized": normalized_symbol,
                "env_key": f"DHAN_SECURITY_ID_{normalized_symbol}",
                "value": os.getenv(f"DHAN_SECURITY_ID_{normalized_symbol}"),
            }
        )

        security_id = os.getenv(
            f"DHAN_SECURITY_ID_{normalized_symbol}"
        )

        if security_id:
            return {
                "security_id": security_id,
                "exchange_segment": _exchange_segment(normalized_symbol),
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

            dhan = dhan_sdk_client()

            security_map = {
                "NIFTY": "13",
                "BANKNIFTY": "25",
                "FINNIFTY": "27",
            }

            security_id = security_map.get(normalized)

            if security_id is None:
                raise MarketDataProviderError(
                    f"Unsupported index {normalized}"
                )

            try:
                raw = dhan.ohlc_data(
                    securities={
                        "IDX_I": [int(security_id)]
                    }
                )

            except Exception as e:
                print("DHAN API ERROR:", repr(e))
                raise

            quote = _extract_quote(raw, security_id)

            logger.debug("Fetched Dhan index quote for %s", normalized)
            quote = _extract_quote(
                raw,
                security_id
            )

            ltp = (
                quote.get("last_price")
                or quote.get("ltp")
            )

            if not ltp:
                raise MarketDataProviderError(
                    "Dhan index LTP missing"
                )

            return {
                "provider": self.provider_name,
                "symbol": normalized,
                "ltp": float(ltp),
                "price": float(ltp),
                "timestamp": self.mark_fetch(),
                "source": "live",
                "exchange": "NSE",
            }
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
    #
    
    def get_candles(
        self,
        symbol: str,
        interval: str,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._require_configured()

        dhan = dhan_sdk_client()

        instrument = self.resolve_instrument(symbol)

        security_id = instrument["security_id"]
        security = (
            int(security_id)
            if str(security_id).isdigit()
            else security_id
        )

        exchange_segment = instrument["exchange_segment"]

        # --------------------------------------------------
        # Dhan supported intervals
        # --------------------------------------------------

        interval_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "25m": 25,
            "60m": 60,
            "1h": 60,
        }

        normalized_interval = str(interval).strip().lower()

        if normalized_interval not in interval_map:
            raise MarketDataProviderError(
                f"Unsupported Dhan candle interval: {interval}. "
                f"Supported intervals: {sorted(interval_map)}"
            )

        dhan_interval = interval_map[normalized_interval]

        # --------------------------------------------------
        # Date range
        # --------------------------------------------------

        to_date = datetime.now(
            ZoneInfo("Asia/Kolkata")
        ).date()

        from_date = (
            to_date
            - timedelta(
                days=max(1, _period_days(period))
            )
        )

        instrument_type = os.getenv(
            "DHAN_INSTRUMENT_TYPE",
            "INDEX",
        )

        logger.info(
            "Dhan candle request "
            "symbol=%s interval=%s dhan_interval=%s "
            "security_id=%s exchange_segment=%s "
            "from=%s to=%s",
            symbol,
            normalized_interval,
            dhan_interval,
            security,
            exchange_segment,
            from_date,
            to_date,
        )

        # --------------------------------------------------
        # Dhan API
        # --------------------------------------------------

        raw = dhan.intraday_minute_data(
            security_id=str(security),
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            interval=dhan_interval,
            oi=False,
        )

        self.mark_fetch()

        candles = _normalize_candles(symbol, raw)

        candles.sort(
            key=lambda c: c["timestamp"]
        )

        # --------------------------------------------------
        # Safety validation
        # --------------------------------------------------

        if candles:
            logger.info(
                "Dhan candles received "
                "symbol=%s requested_interval=%s "
                "dhan_interval=%s candles=%s "
                "first=%s last=%s",
                symbol,
                normalized_interval,
                dhan_interval,
                len(candles),
                candles[0]["timestamp"],
                candles[-1]["timestamp"],
            )

        # --------------------------------------------------
        # Limit
        # --------------------------------------------------

        MAX_LIMIT = 100000

        requested_limit = min(
            int(limit or MAX_LIMIT),
            MAX_LIMIT,
        )

        return candles[-requested_limit:]     
    

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

def _exchange_segment(symbol: str | None = None) -> str:
    print("SYMBOL =", repr(symbol))

    print(
        "ENV LOOKUP =",
        f"DHAN_EXCHANGE_SEGMENT_{symbol.upper()}" if symbol else None,
    )

    print(
        "ENV VALUE =",
        os.getenv(f"DHAN_EXCHANGE_SEGMENT_{symbol.upper()}") if symbol else None,
    )

    print(
        "DEFAULT =",
        os.getenv("DHAN_MARKET_EXCHANGE_SEGMENT"),
    )

    if symbol:
        value = os.getenv(f"DHAN_EXCHANGE_SEGMENT_{symbol.upper()}")
        if value:
            return value
    
    
    return os.getenv("DHAN_MARKET_EXCHANGE_SEGMENT", "NSE")
    
def _period_days(period: str) -> int:
    value = str(period or "1d").lower()

    try:
        if value.endswith("d"):
            return int(value[:-1])

        if value.endswith("w"):
            return int(value[:-1]) * 7

        if value.endswith("mo"):
            return int(value[:-2]) * 30

        if value.endswith("y"):
            return int(value[:-1]) * 365

    except ValueError:
        pass

    return 1

def _extract_quote(raw: Any, security_id: str) -> dict[str, Any]:

    if not isinstance(raw, dict):
        return {}

    data = raw.get("data", raw)

    # Dhan sometimes returns nested data
    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    if not isinstance(data, dict):
        return {}

    idx_data = data.get("IDX_I")

    if isinstance(idx_data, dict):
        quote = idx_data.get(str(security_id))
        if isinstance(quote, dict):
            return quote

    # fallback recursive search
    for value in data.values():
        if isinstance(value, dict):
            found = _extract_quote(value, security_id)
            if found:
                return found

    return {}

def _normalize_candles(symbol: str, raw: Any) -> list[dict[str, Any]]:
    data = raw.get("data", raw) if isinstance(raw, dict) else raw

    rows: list[dict[str, Any]] = []

    if isinstance(data, dict):
        timestamps = data.get("timestamp") or data.get("time") or data.get("start_Time") or []
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        volumes = data.get("volume") or []

        for index, ts in enumerate(timestamps):

            volume = int(_safe_index(volumes, index) or 0)

            # Skip fake Dhan candle
            if volume == 0:
                continue

            dt = datetime.fromtimestamp(
                float(ts),
                ZoneInfo("Asia/Kolkata"),
            )

            # Ignore anything outside NSE trading hours
            if (
                dt.time() < time(9, 15)
                or dt.time() > time(15, 29)
            ):
                continue

            rows.append(
                {
                    "symbol": symbol.upper(),
                    "timestamp": dt.isoformat(),
                    "exchange_timezone": "Asia/Kolkata",
                    "open": _to_float(_safe_index(opens, index)),
                    "high": _to_float(_safe_index(highs, index)),
                    "low": _to_float(_safe_index(lows, index)),
                    "close": _to_float(_safe_index(closes, index)),
                    "volume": volume,
                }
            )

        return rows

    if isinstance(data, list):
        for item in data:

            if not isinstance(item, dict):
                continue

            volume = int(item.get("volume") or 0)

            if volume == 0:
                continue

            ts = item.get("timestamp") or item.get("time") or item.get("start_Time")

            dt = datetime.fromisoformat(
                _timestamp_to_ist(ts)
            )

            if (
                dt.time() < time(9, 15)
                or dt.time() > time(15, 29)
            ):
                continue

            rows.append(
                {
                    "symbol": symbol.upper(),
                    "timestamp": dt.isoformat(),
                    "exchange_timezone": "Asia/Kolkata",
                    "open": _to_float(item.get("open")),
                    "high": _to_float(item.get("high")),
                    "low": _to_float(item.get("low")),
                    "close": _to_float(item.get("close")),
                    "volume": volume,
                }
            )

        return rows

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
