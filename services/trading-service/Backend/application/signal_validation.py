from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.market_api import get_price

MAX_ENTRY_MARKET_DRIFT = float(os.getenv("SIGNAL_MAX_ENTRY_MARKET_DRIFT", "0.01"))
MAX_STOP_DISTANCE = float(os.getenv("SIGNAL_MAX_STOP_DISTANCE", "0.025"))
MIN_RISK_REWARD = float(os.getenv("SIGNAL_MIN_RISK_REWARD", "1.5"))
MIN_SIGNAL_SCORE = float(os.getenv("SIGNAL_MIN_SCORE", "7.0"))
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


def _indicator_value(metadata: dict[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if not _finite_number(value):
        return None
    return float(value)


def _trend_direction(metadata: dict[str, Any]) -> str | None:
    ema_9 = _indicator_value(metadata, "ema_9")
    ema_21 = _indicator_value(metadata, "ema_21")
    ema_50 = _indicator_value(metadata, "ema_50")
    ema_200 = _indicator_value(metadata, "ema_200")

    if None in (ema_9, ema_21, ema_50, ema_200):
        return None
    if ema_9 > ema_21 > ema_50 > ema_200:
        return "UPTREND"
    if ema_9 < ema_21 < ema_50 < ema_200:
        return "DOWNTREND"
    return None


def _trend_aligned(signal: StrategySignal) -> bool:
    trend = _trend_direction(signal.metadata)
    if signal.side == "BUY":
        return trend == "UPTREND"
    if signal.side == "SELL":
        return trend == "DOWNTREND"
    return False


def _rsi_aligned(signal: StrategySignal) -> bool:
    rsi = _indicator_value(signal.metadata, "rsi")
    if rsi is None:
        return False
    if signal.side == "BUY":
        return rsi > 40
    if signal.side == "SELL":
        return rsi < 60
    return False


def _macd_aligned(signal: StrategySignal) -> bool:
    macd = _indicator_value(signal.metadata, "macd")
    macd_signal = _indicator_value(signal.metadata, "macd_signal")
    if macd is None or macd_signal is None:
        return False
    if signal.side == "BUY":
        return macd > macd_signal
    if signal.side == "SELL":
        return macd < macd_signal
    return False


def _momentum_aligned(signal: StrategySignal) -> bool:
    return _rsi_aligned(signal) and _macd_aligned(signal)


def _zone_confirmed(signal: StrategySignal) -> bool:
    strategy_name = signal.strategy_name.lower()
    metadata_values = " ".join(str(value).lower() for value in signal.metadata.values())
    return any(
        marker in f"{strategy_name} {metadata_values}"
        for marker in ("supply", "demand", "fvg")
    )


def _is_market_aligned(signal: StrategySignal, market_price: float) -> bool:
    if market_price <= 0:
        return False
    drift = abs(float(signal.entry_price) - market_price) / market_price
    return drift < MAX_ENTRY_MARKET_DRIFT


def _risk_reward(signal: StrategySignal) -> float:
    risk = abs(float(signal.entry_price) - float(signal.stop_loss))
    reward = abs(float(signal.target_price) - float(signal.entry_price))
    if risk <= 0:
        return 0.0
    return reward / risk


def _stop_distance(signal: StrategySignal) -> float:
    entry = float(signal.entry_price)
    if entry <= 0:
        return 1.0
    return abs(entry - float(signal.stop_loss)) / entry


def _score(signal: StrategySignal) -> float:
    for key in ("total_score", "score"):
        value = signal.metadata.get(key)
        if _finite_number(value):
            return float(value)
    return 0.0


def _quality_rank(signal: StrategySignal) -> tuple[float, float]:
    return _score(signal), _risk_reward(signal)


def _is_high_quality(signal: StrategySignal) -> bool:
    if _score(signal) < MIN_SIGNAL_SCORE:
        return False
    if _risk_reward(signal) < MIN_RISK_REWARD:
        return False
    if _stop_distance(signal) > MAX_STOP_DISTANCE:
        return False
    if not _trend_aligned(signal):
        return False
    if not _momentum_aligned(signal):
        return False

    confluence_count = sum(
        [
            _trend_aligned(signal),
            _macd_aligned(signal),
            _rsi_aligned(signal),
            _zone_confirmed(signal),
        ]
    )
    if confluence_count < 2:
        return False
    return True


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
        if not _is_high_quality(signal):
            continue

        signal.metadata["data_source"] = source_tag
        signal.metadata["quality"] = "high"
        signal.metadata["trend"] = _trend_direction(signal.metadata)
        signal.metadata["confluence_count"] = sum(
            [
                _trend_aligned(signal),
                _macd_aligned(signal),
                _rsi_aligned(signal),
                _zone_confirmed(signal),
            ]
        )
        signal.metadata["risk_reward"] = round(_risk_reward(signal), 2)
        signal.metadata["market_price"] = round(float(market_price), 4)
        signal.metadata["entry_market_drift_pct"] = round(
            abs(float(signal.entry_price) - float(market_price)) / float(market_price) * 100,
            3,
        )
        valid_signals.append(signal)

    if not valid_signals:
        return [], source_tag

    return [max(valid_signals, key=_quality_rank)], source_tag
