from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Backend.application.signal_quality import decide_signal
from Backend.domain.models.signal import StrategySignal


def _trend_candles(count: int, *, start_price: float = 100.0, step: float = 1.0) -> list[dict]:
    start = datetime(2026, 5, 22, 3, 0, tzinfo=timezone.utc)
    price = start_price
    candles = []
    for index in range(count):
        open_price = price
        close = price + step
        candles.append({
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": max(open_price, close) + 0.8,
            "low": min(open_price, close) - 0.3,
            "close": close,
            "volume": 1000 + index * 20,
        })
        price = close
    return candles


def _signal(*, score: float = 8, side: str = "BUY", minutes_back: int = 0) -> StrategySignal:
    latest = datetime(2026, 5, 22, 3, 39, tzinfo=timezone.utc)
    return StrategySignal(
        strategy_name="test",
        symbol="NIFTY",
        side=side,
        entry_price=139,
        stop_loss=130 if side == "BUY" else 145,
        target_price=150 if side == "BUY" else 125,
        signal_time=latest - timedelta(minutes=minutes_back),
        metadata={"score": score, "quantity": 75},
    )


def test_stale_signal_rejection():
    decision = decide_signal(_signal(minutes_back=3), candles_1m=_trend_candles(40), candles_15m=_trend_candles(40))

    assert decision.allowed is False
    assert decision.status == "STALE"
    assert decision.reason == "STALE_SIGNAL"


def test_low_score_rejection():
    decision = decide_signal(_signal(score=5), candles_1m=_trend_candles(40), candles_15m=_trend_candles(40))

    assert decision.allowed is False
    assert decision.reason == "LOW_SCORE"


def test_mtf_conflict_rejection():
    decision = decide_signal(
        _signal(side="SELL"),
        candles_1m=_trend_candles(40),
        candles_15m=_trend_candles(40),
    )

    assert decision.allowed is False
    assert decision.reason == "MTF_CONFLICT"
