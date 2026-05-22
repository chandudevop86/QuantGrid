from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.signal import StrategySignal


SignalStatus = Literal["ACTIVE", "STALE", "REJECTED"]
RejectReason = Literal[
    "LOW_SCORE",
    "STALE_SIGNAL",
    "CHOPPY_MARKET",
    "MTF_CONFLICT",
    "DAILY_LOSS_LIMIT",
    "MAX_TRADES_PER_DAY",
    "MAX_CONSECUTIVE_LOSSES",
    "OK",
]


@dataclass(frozen=True, slots=True)
class MarketRegime:
    regime: str
    reason: str
    atr_pct: float


@dataclass(frozen=True, slots=True)
class SignalDecision:
    allowed: bool
    status: SignalStatus
    reason: RejectReason
    signal_age_minutes: float | None
    latest_candle_time: str | None
    score: float
    regime: str
    mtf_bias: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def min_signal_score() -> float:
    try:
        return float(os.getenv("MIN_SIGNAL_SCORE", os.getenv("SIGNAL_MIN_SCORE", "7")))
    except ValueError:
        return 7.0


def max_signal_age_minutes() -> float:
    try:
        return float(os.getenv("SIGNAL_MAX_AGE_MINUTES", "2"))
    except ValueError:
        return 2.0


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        timestamp = value
    else:
        try:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _score(signal: StrategySignal) -> float:
    for key in ("total_score", "score"):
        value = signal.metadata.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def latest_candle_time(candles: list[dict[str, Any]]) -> datetime | None:
    if not candles:
        return None
    return _parse_timestamp(candles[-1].get("timestamp"))


def signal_age_minutes(signal: StrategySignal, candles: list[dict[str, Any]]) -> float | None:
    latest = latest_candle_time(candles)
    signal_time = _parse_timestamp(signal.signal_time)
    if latest is None or signal_time is None:
        return None
    return round(max(0.0, (latest - signal_time).total_seconds() / 60.0), 2)


def detect_market_regime(candles: list[dict[str, Any]]) -> MarketRegime:
    if len(candles) < 20:
        return MarketRegime("CHOPPY", "Insufficient candles for regime confidence.", 0.0)

    frame = IndicatorService().prepare(candles)
    row = frame.iloc[-1]
    close = max(float(row["close"]), 0.01)
    atr_pct = float(row.get("atr_14", 0.0) or 0.0) / close
    ema9, ema21, ema50, ema200 = (float(row[key]) for key in ("ema_9", "ema_21", "ema_50", "ema_200"))
    recent = frame.tail(12)
    range_size = float(recent["high"].max() - recent["low"].min())
    body_sum = float(recent["body_size"].sum())

    if atr_pct < 0.00035:
        return MarketRegime("LOW_VOLATILITY", "ATR percent is below tradable threshold.", round(atr_pct, 6))
    if atr_pct > 0.004:
        return MarketRegime("HIGH_VOLATILITY", "ATR percent is elevated; widen filters and reduce risk.", round(atr_pct, 6))
    if range_size > 0 and body_sum / range_size < 2.2:
        return MarketRegime("CHOPPY", "Recent bodies are inefficient inside the active range.", round(atr_pct, 6))
    if ema9 > ema21 > ema50 > ema200 or ema9 < ema21 < ema50 < ema200:
        return MarketRegime("TRENDING", "EMA stack is directionally aligned.", round(atr_pct, 6))
    return MarketRegime("RANGING", "No clean EMA stack; market is rotating.", round(atr_pct, 6))


def mtf_bias(candles_15m: list[dict[str, Any]] | None) -> str:
    if not candles_15m or len(candles_15m) < 20:
        return "UNKNOWN"
    frame = IndicatorService().prepare(candles_15m)
    row = frame.iloc[-1]
    ema9, ema21, ema50, ema200 = (float(row[key]) for key in ("ema_9", "ema_21", "ema_50", "ema_200"))
    close = float(row["close"])
    if close > float(row["vwap"]) and ema9 > ema21 > ema50 > ema200:
        return "BULLISH"
    if close < float(row["vwap"]) and ema9 < ema21 < ema50 < ema200:
        return "BEARISH"
    return "RANGE"


def decide_signal(
    signal: StrategySignal,
    *,
    candles_1m: list[dict[str, Any]],
    candles_15m: list[dict[str, Any]] | None = None,
) -> SignalDecision:
    latest = latest_candle_time(candles_1m)
    age = signal_age_minutes(signal, candles_1m)
    score = _score(signal)
    regime = detect_market_regime(candles_1m)
    bias = mtf_bias(candles_15m)

    if age is None or age > max_signal_age_minutes():
        return SignalDecision(False, "STALE", "STALE_SIGNAL", age, latest.isoformat() if latest else None, score, regime.regime, bias)
    if score < min_signal_score():
        return SignalDecision(False, "REJECTED", "LOW_SCORE", age, latest.isoformat() if latest else None, score, regime.regime, bias)
    if regime.regime == "CHOPPY":
        return SignalDecision(False, "REJECTED", "CHOPPY_MARKET", age, latest.isoformat() if latest else None, score, regime.regime, bias)
    if (signal.side == "BUY" and bias == "BEARISH") or (signal.side == "SELL" and bias == "BULLISH"):
        return SignalDecision(False, "REJECTED", "MTF_CONFLICT", age, latest.isoformat() if latest else None, score, regime.regime, bias)

    return SignalDecision(True, "ACTIVE", "OK", age, latest.isoformat() if latest else None, score, regime.regime, bias)


def split_signals(
    signals: list[StrategySignal],
    *,
    candles_1m: list[dict[str, Any]],
    candles_15m: list[dict[str, Any]] | None = None,
) -> tuple[list[StrategySignal], list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[StrategySignal] = []
    rejected: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for signal in signals:
        decision = decide_signal(signal, candles_1m=candles_1m, candles_15m=candles_15m)
        signal.metadata.update(decision.to_dict())
        if decision.allowed:
            active.append(signal)
        elif decision.status == "STALE":
            stale.append({"signal": signal, "decision": decision.to_dict()})
        else:
            rejected.append({"signal": signal, "decision": decision.to_dict()})
    return active, rejected, stale
