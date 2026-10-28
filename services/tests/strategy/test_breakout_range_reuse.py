"""Regression tests for breakout rolling-range reuse (offline)."""

import pandas as pd
import pytest

from Backend.domain.breakout.detector import BreakoutDetectionEngine


@pytest.mark.parametrize("lookback", [5, 20])
def test_prepared_extrema_match_raw_windows(lookback):
    n = 80
    frame = pd.DataFrame({
        "high": [100.0 + i * 0.17 + (i % 7) for i in range(n)],
        "low": [95.0 + i * 0.17 - (i % 5) for i in range(n)],
        "atr_14": [2.0] * n,
    })
    prepared = frame.copy()
    prepared["breakout_high"] = prepared["high"].shift(1).rolling(lookback, min_periods=lookback).max()
    prepared["breakout_low"] = prepared["low"].shift(1).rolling(lookback, min_periods=lookback).min()
    detector = BreakoutDetectionEngine(lookback=lookback)
    for i in range(n):
        baseline = detector.range_at(frame, i)
        optimized = detector.range_at(prepared, i)
        assert optimized == baseline


def test_prepared_extrema_do_not_use_current_candle():
    frame = pd.DataFrame({
        "high": [10.0] * 20 + [1000.0],
        "low": [5.0] * 20 + [-1000.0],
        "atr_14": [1.0] * 21,
    })
    frame["breakout_high"] = frame["high"].shift(1).rolling(20, min_periods=20).max()
    frame["breakout_low"] = frame["low"].shift(1).rolling(20, min_periods=20).min()
    result = BreakoutDetectionEngine(lookback=20).range_at(frame, 20)
    assert result is not None
    assert result.high == 10.0
    assert result.low == 5.0
