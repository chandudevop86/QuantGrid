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


def test_stale_underlying_candles_rejected_even_when_signal_matches_candle_time():
    # Regression test for a bug where decide_signal() passed the LATEST CANDLE'S OWN
    # timestamp as the reference "current time" to validate_live_candle(), instead of the
    # real current time. That made the staleness check tautological -- a candle is always
    # "fresh" relative to itself, no matter how many real-world hours old it actually is.
    # This test builds candles that are genuinely hours old relative to actual now, but keeps
    # signal_time exactly in step with the latest candle (minutes_back=0) so the OTHER,
    # already-correct relative check (signal_age_minutes) passes -- only the absolute
    # staleness check can catch this. Before the fix, this signal would have been wrongly
    # allowed through as fresh.
    real_now = datetime.now(timezone.utc)
    stale_start = real_now - timedelta(hours=18)
    price = 100.0
    candles = []
    for index in range(40):
        open_price = price
        close = price + 1.0
        candles.append({
            "timestamp": (stale_start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": max(open_price, close) + 0.8,
            "low": min(open_price, close) - 0.3,
            "close": close,
            "volume": 1000 + index * 20,
        })
        price = close
    latest_candle_time = stale_start + timedelta(minutes=39)

    signal = StrategySignal(
        strategy_name="test",
        symbol="NIFTY",
        side="BUY",
        entry_price=139,
        stop_loss=130,
        target_price=150,
        signal_time=latest_candle_time,  # matches the (stale) latest candle exactly: age=0
        metadata={"score": 8, "quantity": 75},
    )

    decision = decide_signal(signal, candles_1m=candles, candles_15m=candles)

    assert decision.allowed is False
    assert decision.status == "STALE"


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
