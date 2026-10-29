"""Safety regression tests for the experimental backtest cache."""

import pandas as pd
import pytest

from Backend.domain.models.context import StrategyContext
from Backend.domain.strategies.backtest_cache_context import (
    allow_backtest_cache,
)
from Backend.domain.strategies.base import BaseStrategy
from Backend.domain.strategies.breakout import BreakoutStrategy


def candles():
    return pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-10-26 09:15",
            periods=30,
            freq="min",
            tz="Asia/Kolkata",
        ),
        "open": [100.0] * 30,
        "high": [102.0] * 30,
        "low": [98.0] * 30,
        "close": [100.0] * 30,
        "volume": [1000] * 30,
    })


def context(prepared):
    return StrategyContext(
        symbol="NIFTY",
        capital=100000,
        risk_pct=1.0,
        rr_ratio=2.0,
        params={"_backtest_prepared_frame": prepared},
    )


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_rejects_modified_cached_ohlcv(column):
    raw = candles()
    prepared = raw.copy()
    prepared.loc[10, column] += 50

    with allow_backtest_cache():
        with pytest.raises(ValueError, match="does not match"):
            BreakoutStrategy().run(raw, context(prepared))


def test_rejects_wrong_dataset_length():
    raw = candles()
    prepared = raw.iloc[:-1].copy()

    with allow_backtest_cache():
        with pytest.raises(ValueError, match="count mismatch"):
            BreakoutStrategy().run(raw, context(prepared))


def test_rejects_wrong_timestamps():
    raw = candles()
    prepared = raw.copy()
    prepared.loc[10, "timestamp"] += pd.Timedelta(minutes=5)

    with allow_backtest_cache():
        with pytest.raises(ValueError, match="does not match"):
            BreakoutStrategy().run(raw, context(prepared))


def test_rejects_incompatible_strategy():
    class OtherStrategy(BaseStrategy):
        def generate_signals(self, candles, context):
            return []

        def calculate_levels(self, candles, index, side, context):
            return (0.0, 0.0)

    raw = candles()

    with allow_backtest_cache():
        with pytest.raises(ValueError, match="restricted"):
            OtherStrategy().run(raw, context(raw.copy()))


def test_cache_failure_propagates():
    from unittest.mock import Mock

    from Backend.trading_system.backtesting import BacktestEngine

    engine = BacktestEngine()
    engine.trading_service = Mock()
    engine.trading_service.run_strategy.side_effect = RuntimeError(
        "Simulated cache execution failure"
    )

    cache = Mock()
    cache.prefix.side_effect = RuntimeError(
        "Simulated cache preparation failure"
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated cache preparation failure",
    ):
        engine._generate_signal(
            frame=candles(),
            index=20,
            strategy_name="breakout",
            symbol="NIFTY",
            capital=100000,
            risk_pct=1.0,
            rr_ratio=2.0,
            min_score=7.0,
            indicator_cache=cache,
        )


def test_uncached_signal_failure_preserves_existing_behavior():
    from unittest.mock import Mock

    from Backend.trading_system.backtesting import BacktestEngine

    engine = BacktestEngine()
    engine.trading_service = Mock()
    engine.trading_service.run_strategy.side_effect = RuntimeError(
        "Simulated strategy failure"
    )

    result = engine._generate_signal(
        frame=candles(),
        index=20,
        strategy_name="breakout",
        symbol="NIFTY",
        capital=100000,
        risk_pct=1.0,
        rr_ratio=2.0,
        min_score=7.0,
        indicator_cache=None,
    )

    assert result is None
