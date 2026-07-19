from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from Backend.application.candle_validation import normalize_timestamp, validate_live_candle, validation_settings
from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.market_api import get_price

MAX_ENTRY_MARKET_DRIFT = float(os.getenv("SIGNAL_MAX_ENTRY_MARKET_DRIFT", "0.01"))
MAX_STOP_DISTANCE = float(os.getenv("SIGNAL_MAX_STOP_DISTANCE", "0.025"))
MIN_RISK_REWARD = float(os.getenv("SIGNAL_MIN_RISK_REWARD", "1.5"))
MIN_SIGNAL_SCORE = float(os.getenv("SIGNAL_MIN_SCORE", "7.0"))
MAX_CANDLE_AGE_SECONDS = validation_settings().reject_after_seconds
LIVE_SOURCE = "yahoo-finance"
DEMO_SOURCES = {"yahoo-finance", "sample-fallback", "stored-live-cache"}


def _is_usable_market_source(source: str | None) -> bool:
    value = str(source or "").lower()
    return bool(value) and value not in {"sample-fallback", "stored-live-cache"}


def data_source_tag(source: str | None) -> str:
    if source == LIVE_SOURCE:
        return "demo"
    return "live" if _is_usable_market_source(source) else "cached"


def _parse_timestamp(value: Any) -> datetime | None:
    timestamp = normalize_timestamp(value)
    return timestamp.astimezone(timezone.utc) if timestamp else None


def _latest_candle(candles: list[dict[str, Any]]) -> dict[str, Any] | None:
    return candles[-1] if candles else None


def candle_freshness(candles: list[dict[str, Any]]) -> dict[str, Any]:
    validation = validate_live_candle(candles)
    return {
        "server_time": validation.server_time,
        "server_time_ist": validation.server_time_ist,
        "latest_candle_at": validation.latest_candle,
        "latest_candle_at_ist": validation.latest_candle_ist,
        "latest_candle_age_seconds": validation.delay_seconds,
        "max_candle_age_seconds": MAX_CANDLE_AGE_SECONDS,
        "market_status": validation.market_status,
        "ui_status": validation.ui_status,
        "market_live": validation.market_live,
        "is_recent": validation.valid,
        "diagnostics": validation.diagnostics,
        "warnings": validation.warnings,
    }


def _is_recent(candle: dict[str, Any]) -> bool:
    return validate_live_candle([candle]).valid


def _matches_latest_candle(signal: StrategySignal, latest_candle: dict[str, Any]) -> bool:
    signal_time = _parse_timestamp(signal.signal_time)
    candle_time = _parse_timestamp(latest_candle.get("timestamp"))
    
    print("=" * 60)
    print("SIGNAL TIME :", signal_time)
    print("LATEST TIME :", candle_time)    
    
    if signal_time is None or candle_time is None:
        return False

    return abs((signal_time - candle_time).total_seconds()) <= 60


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

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _is_mean_reversion(signal: StrategySignal) -> bool:
    strategy_name = signal.strategy_name.lower()
    setup = str(signal.metadata.get("setup", "")).lower()
    return "mean reversion" in strategy_name or setup == "enhanced_mean_reversion"


def _is_crt_tbs(signal: StrategySignal) -> bool:
    strategy_key = str(signal.metadata.get("strategy_key") or "").lower()
    return strategy_key in {"crt_tbs", "cbt"} or "crt tbs" in signal.strategy_name.lower() or signal.strategy_name.lower() == "cbt"


def _is_mtfa(signal: StrategySignal) -> bool:
    return str(signal.metadata.get("strategy_key") or "").lower() == "mtfa" or signal.strategy_name.lower() == "mtfa"


def _mean_reversion_high_quality(signal: StrategySignal) -> bool:
    if _score(signal) < 5.0:
        return False
    if _risk_reward(signal) < MIN_RISK_REWARD:
        return False
    if _stop_distance(signal) > MAX_STOP_DISTANCE:
        return False
    if signal.metadata.get("market_regime") != "ranging":
        return False
    if not _trend_aligned(signal):
        return False

    score_components = signal.metadata.get("score_components")
    if not isinstance(score_components, dict):
        return False

    required_components = ["rsi_extreme", "mean_deviation", "trend_alignment", "macd_confirmation"]
    return all(float(score_components.get(component) or 0.0) > 0.0 for component in required_components)


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
    if _is_mtfa(signal):
        return (
            _score(signal) >= 7.0
            and _risk_reward(signal) >= 1.99
            and bool(signal.metadata.get("mtfa_valid"))
            and bool(signal.metadata.get("mtfa_15m_trigger"))
        )

    if _is_crt_tbs(signal):
        return (
            _score(signal) >= 7.0
            and _risk_reward(signal) >= 1.99
            and bool(signal.metadata.get("liquidity_sweep"))
            and str(signal.metadata.get("quality_tier") or "").upper() in {"MEDIUM QUALITY", "HIGH QUALITY"}
        )

    if _is_mean_reversion(signal):
        return _mean_reversion_high_quality(signal)

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
    if not _zone_confirmed(signal):
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
    candle_validation = validate_live_candle(candles, source=candle_source, mode="paper")
    if not _is_usable_market_source(candle_source) or latest is None or not candle_validation.valid_for_analysis:
        return [], source_tag

    price_response = get_price(symbol)
    if not _is_usable_market_source(price_response.get("source")):
        return [], data_source_tag(price_response.get("source"))

    market_price = price_response.get("price")
    if not _finite_number(market_price):
        return [], data_source_tag(price_response.get("source"))

    valid_signals: list[StrategySignal] = []
    for signal in signals:
        if latest is None or not _matches_latest_candle(signal, latest):
            continue
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


def diagnose_signal_run(
    signals: list[StrategySignal],
    *,
    symbol: str,
    candles: list[dict[str, Any]],
    candle_source: str | None,
) -> list[str]:
    diagnostics: list[str] = []
    source_tag = data_source_tag(candle_source)
    latest = _latest_candle(candles)
    validation = validate_live_candle(candles, source=candle_source, mode="paper")
    freshness = candle_freshness(candles)

    if latest is None:
        return ["No candle data available for diagnostics."]
    if not _is_usable_market_source(candle_source):
        diagnostics.append(f"Market data source is {source_tag}; validator requires a usable market data provider.")
    diagnostics.extend(validation.diagnostics)
    diagnostics.extend(validation.warnings)
    if not validation.valid:
        latest_at = freshness.get("latest_candle_at") or "unknown"
        age_seconds = freshness.get("latest_candle_age_seconds")
        if isinstance(age_seconds, (int, float)) and age_seconds < 0:
            diagnostics.append(
                f"Latest candle timestamp {latest_at} is ahead of the server clock; check clock synchronization."
            )
        elif isinstance(age_seconds, (int, float)):
            diagnostics.append(
                "Latest candle is stale during live market validation "
                f"(latest {latest_at}, age {age_seconds:.0f}s, limit {MAX_CANDLE_AGE_SECONDS}s)."
            )
        else:
            diagnostics.append(
                "Latest candle could not be validated "
                f"(latest timestamp {latest_at} could not be parsed)."
            )

    if not signals:
        diagnostics.append("Strategy generated no raw setup from the supplied candles.")
        return diagnostics

    try:
        price_response = get_price(symbol)
    except Exception as exc:
        price_response = {"source": None, "price": None}
        diagnostics.append(f"Live market price is unavailable: {exc}.")
    market_price = price_response.get("price")
    if not _is_usable_market_source(price_response.get("source")):
        diagnostics.append("Live market price is unavailable; signal cannot be market-aligned.")
    if not _finite_number(market_price):
        diagnostics.append("Market price is not a finite number.")

    for signal in signals:
        prefix = f"{signal.strategy_name} {signal.side}"
        reasons: list[str] = []
        if not _matches_latest_candle(signal, latest):
            reasons.append("signal is not on the latest candle")
        if not _is_valid_trade_shape(signal):
            reasons.append("entry/stop/target shape is invalid")
        if not _valid_indicator_metadata(signal.metadata):
            reasons.append("indicator metadata is missing or invalid")
        if _finite_number(market_price) and not _is_market_aligned(signal, float(market_price)):
            reasons.append("entry is too far from live market price")
        if _score(signal) < MIN_SIGNAL_SCORE:
            reasons.append(f"score {_score(signal):.1f} is below validator threshold {MIN_SIGNAL_SCORE:.1f}")
        if _risk_reward(signal) < MIN_RISK_REWARD:
            reasons.append(f"RR {_risk_reward(signal):.2f} is below {MIN_RISK_REWARD:.2f}")
        if _stop_distance(signal) > MAX_STOP_DISTANCE:
            reasons.append(f"stop distance {_stop_distance(signal) * 100:.2f}% exceeds {MAX_STOP_DISTANCE * 100:.2f}%")
        if not _trend_aligned(signal):
            reasons.append("trend alignment failed")
        if not _momentum_aligned(signal):
            reasons.append("RSI/MACD momentum alignment failed")
        if not _zone_confirmed(signal):
            reasons.append("zone/FVG/supply-demand confluence not present")
        if reasons:
            diagnostics.append(f"{prefix} rejected: {', '.join(reasons)}.")

    if not diagnostics:
        diagnostics.append("Raw signal passed local diagnostics but was not selected by final quality ranking.")
    return diagnostics
