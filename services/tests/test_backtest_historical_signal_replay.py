"""Prevent replay of historical strategy signals at later backtest candles."""

from datetime import timedelta

import pandas as pd
import pytest

from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.backtesting import BacktestEngine


def _frame():
    times = pd.date_range("2026-10-28 09:15", periods=3, freq="min", tz="Asia/Kolkata")
    return pd.DataFrame({
        "timestamp": times,
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.0, 101.0, 102.0],
        "volume": [1000, 1000, 1000],
    })


def _signal(timestamp):
    return StrategySignal(
        strategy_name="breakout", symbol="NIFTY", side="BUY",
        entry_price=100.0, stop_loss=98.0, target_price=104.0,
        signal_time=timestamp, metadata={"score": 10},
    )


class FakeService:
    def __init__(self, signals):
        self.signals = signals

    def run_strategy(self, **kwargs):
        return self.signals


def _generate(signals):
    engine = BacktestEngine()
    engine.trading_service = FakeService(signals)
    return engine._generate_signal(_frame(), 2, "breakout", "NIFTY", 100000, 1, 2, 7)


def test_historical_signal_is_not_replayed():
    assert _generate([_signal(_frame().iloc[0]["timestamp"])]) is None


def test_future_signal_is_not_accepted():
    assert _generate([_signal(_frame().iloc[2]["timestamp"] + timedelta(minutes=1))]) is None


def test_current_signal_is_accepted():
    current = _signal(_frame().iloc[2]["timestamp"])
    assert _generate([current]) is current


def test_timezone_equivalent_signal_is_accepted():
    current = _signal(_frame().iloc[2]["timestamp"].tz_convert("UTC"))
    assert _generate([current]) is current


def test_current_signal_selected_after_older_signal():
    frame = _frame()
    old = _signal(frame.iloc[0]["timestamp"])
    current = _signal(frame.iloc[2]["timestamp"])
    assert _generate([old, current]) is current


def test_naive_utc_signal_matches_aware_candle():
    frame = _frame()
    naive_utc = frame.iloc[2]["timestamp"].tz_convert("UTC").tz_localize(None)
    current = _signal(naive_utc)
    assert _generate([current]) is current
