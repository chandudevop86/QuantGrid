from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.market_api import get_price

MAX_ENTRY_MARKET_DRIFT = 0.02
MAX_CANDLE_AGE_SECONDS = 5 * 60
LIVE_SOURCE = "yahoo-finance"


def data_source_tag(source: str | None) -> str:
    return "live" if source == LIVE_SOURCE else "cached"


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None

    try:
        if isinstance(value, datetime):
            timestamp = value
        else:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _latest_candle(candles: list[dict[str, Any]]) -> dict[str, Any] | None:
    return candles[-1] if candles else None


def _is_recent(candle: dict[str, Any]) -> bool:
    timestamp = _parse_timestamp(candle.get("timestamp"))
    if timestamp is None:
        return False

    age = datetime.now(timezone.utc) - timestamp
    return 0 <= age.total_seconds() <= MAX_CANDLE_AGE_SECONDS


def _is_valid_trade_shape(signal: StrategySignal) -> bool:
    entry = float(signal.entry_price)
    stop = float(signal.stop_loss)
    target = float(signal.target_price)

    if entry <= 0 or stop <= 0 or target <= 0:
        return False
    if signal.side == "BUY":
        return stop < entry < target
    if signal.side == "SELL":
        return target < entry < stop
    return False


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _valid_indicator_metadata(metadata: dict[str, Any]) -> bool:
    rsi = metadata.get("rsi")
    if rsi is not None and (not _finite_number(rsi) or not 0 <= float(rsi) <= 100):
        return False

    for key, value in metadata.items():
        if key.startswith("ema") and value is not None and not _finite_number(value):
            return False
        if key.startswith("macd") and value is not None and not _finite_number(value):
            return False

    return True


def _is_market_aligned(signal: StrategySignal, market_price: float) -> bool:
    if market_price <= 0:
        return False
    drift = abs(float(signal.entry_price) - market_price) / market_price
    return drift < MAX_ENTRY_MARKET_DRIFT


def validate_signals(
    signals: list[StrategySignal],
    *,
    symbol: str,
    candles: list[dict[str, Any]],
    candle_source: str | None,
) -> tuple[list[StrategySignal], str]:
    source_tag = data_source_tag(candle_source)
    latest = _latest_candle(candles)
    if candle_source != LIVE_SOURCE or latest is None or not _is_recent(latest):
        return [], source_tag

    price_response = get_price(symbol)
    if price_response.get("source") != LIVE_SOURCE:
        return [], data_source_tag(price_response.get("source"))

    market_price = price_response.get("price")
    if not _finite_number(market_price):
        return [], data_source_tag(price_response.get("source"))

    valid_signals: list[StrategySignal] = []
    for signal in signals:
        if not _is_valid_trade_shape(signal):
            continue
        if not _valid_indicator_metadata(signal.metadata):
            continue
        if not _is_market_aligned(signal, float(market_price)):
            continue

        signal.metadata["data_source"] = source_tag
        valid_signals.append(signal)

    return valid_signals, source_tag
