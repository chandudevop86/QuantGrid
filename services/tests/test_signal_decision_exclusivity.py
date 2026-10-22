"""Safety regression tests: one evaluated signal must have one terminal decision."""
from __future__ import annotations

from Backend.application import signal_quality
from Backend.application.signal_quality import SignalDecision, split_signals


def test_one_signal_cannot_be_accepted_and_rejected(monkeypatch):
    """A bullish higher-timeframe decision must reject a SELL setup."""
    signal = type("Signal", (), {"metadata": {}, "side": "SELL"})()
    decision = SignalDecision(
        allowed=False,
        status="REJECTED",
        reason="MTF_CONFLICT",
        signal_age_minutes=0.0,
        latest_candle_time="2026-10-22T09:05:00+00:00",
        score=9.0,
        regime="TRENDING",
        mtf_bias="BULLISH",
    )
    monkeypatch.setattr(signal_quality, "decide_signal", lambda *_args, **_kw: decision)
    accepted, rejected, stale = split_signals([signal], candles_1m=[], candles_by_timeframe={})
    assert accepted == []
    assert stale == []
    assert len(rejected) == 1
    assert rejected[0]["decision"]["reason"] == "MTF_CONFLICT"
    assert rejected[0]["signal"] is signal


def test_accepted_signal_does_not_appear_in_rejected_or_stale(monkeypatch):
    signal = type("Signal", (), {"metadata": {}, "side": "SELL"})()
    decision = SignalDecision(
        allowed=True,
        status="ACTIVE",
        reason="OK",
        signal_age_minutes=0.0,
        latest_candle_time="2026-10-22T09:05:00+00:00",
        score=9.0,
        regime="TRENDING",
        mtf_bias="BEARISH",
    )
    monkeypatch.setattr(signal_quality, "decide_signal", lambda *_args, **_kw: decision)
    accepted, rejected, stale = split_signals([signal], candles_1m=[], candles_by_timeframe={})
    assert accepted == [signal]
    assert rejected == []
    assert stale == []
