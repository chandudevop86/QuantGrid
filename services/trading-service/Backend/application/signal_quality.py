from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from Backend.application.candle_validation import normalize_timestamp, validate_live_candle, validation_settings

from Backend.domain.models.signal import StrategySignal
from Backend.application.market_regime_consensus_engine import MarketRegimeConsensusEngine




market_regime_engine = MarketRegimeConsensusEngine()

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
        return 5.0


def _parse_timestamp(value: Any) -> datetime | None:
    timestamp = normalize_timestamp(value)
    return timestamp.astimezone(timezone.utc) if timestamp else None


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




def decide_signal(
    signal: StrategySignal,
    *,
    candles_1m: list[dict[str, Any]],
    candles_by_timeframe: dict[str, list[dict[str, Any]]],
) -> SignalDecision:
    latest = latest_candle_time(candles_1m)
    age = signal_age_minutes(signal, candles_1m)
    score = _score(signal)
    regime = market_regime_engine.build_market_regime(candles_by_timeframe)
    bias = regime.bias
    candle_validation = validate_live_candle(candles_1m, mode="paper")
    wall_clock_age_seconds = (
        max(0.0, (datetime.now(timezone.utc) - latest).total_seconds())
        if latest is not None
        else None
    )
    latest_time = latest.isoformat() if latest else None

    if age is None or age > max_signal_age_minutes():
        return SignalDecision(
            False,
            "STALE",
            "STALE_SIGNAL",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    if (
        wall_clock_age_seconds is None
        or wall_clock_age_seconds > validation_settings().reject_after_seconds
    ):
        return SignalDecision(
            False,
            "STALE",
            "STALE_SIGNAL",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    if not candle_validation.valid_for_analysis:
        return SignalDecision(
            False,
            "STALE",
            "STALE_SIGNAL",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    if score < min_signal_score():
        return SignalDecision(
            False,
            "REJECTED",
            "LOW_SCORE",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    if regime.regime in {
        "CHOPPY",
        "HIGH_VOLATILITY",
    }:
        return SignalDecision(
            False,
            "REJECTED",
            "CHOPPY_MARKET",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    if (
        signal.side == "BUY"
        and bias in {"BEARISH", "STRONG_BEARISH"}
    ):
        return SignalDecision(
            False,
            "REJECTED",
            "MTF_CONFLICT",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    if (
        signal.side == "SELL"
        and bias in {"BULLISH", "STRONG_BULLISH"}
    ):
        return SignalDecision(
            False,
            "REJECTED",
            "MTF_CONFLICT",
            age,
            latest_time,
            score,
            regime.regime,
            bias,
        )

    return SignalDecision(
        True,
        "ACTIVE",
        "OK",
        age,
        latest_time,
        score,
        regime.regime,
        bias,
    )
    

def split_signals(
    signals: list[StrategySignal],
    *,
    candles_1m: list[dict[str, Any]],
    candles_by_timeframe: dict[str, list[dict[str, Any]]],
) -> tuple[list[StrategySignal], list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[StrategySignal] = []
    rejected: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for signal in signals:
        decision = decide_signal(signal, candles_1m=candles_1m, candles_by_timeframe=candles_by_timeframe)
        signal.metadata.update(decision.to_dict())
        if decision.allowed:
            active.append(signal)
        elif decision.status == "STALE":
            stale.append({"signal": signal, "decision": decision.to_dict()})
        else:
            rejected.append({"signal": signal, "decision": decision.to_dict()})
    return active, rejected, stale
