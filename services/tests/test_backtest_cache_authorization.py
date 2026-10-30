"""Regression tests for internal backtest cache authorization."""

import pandas as pd
import pytest

from Backend.domain.strategies.backtest_cache_context import (
    allow_backtest_cache,
    backtest_cache_allowed,
)


def test_cache_authorization_disabled_by_default():
    assert backtest_cache_allowed() is False


def test_cache_authorization_scoped_and_restored():
    assert backtest_cache_allowed() is False

    with allow_backtest_cache():
        assert backtest_cache_allowed() is True

    assert backtest_cache_allowed() is False


def test_cache_authorization_restored_after_exception():
    with pytest.raises(RuntimeError):
        with allow_backtest_cache():
            assert backtest_cache_allowed() is True
            raise RuntimeError("test")

    assert backtest_cache_allowed() is False


def test_cache_authorization_does_not_leak_between_contexts():
    import contextvars

    with allow_backtest_cache():
        assert backtest_cache_allowed() is True

    isolated = contextvars.Context()
    assert isolated.run(backtest_cache_allowed) is False


def test_external_prepared_frame_cannot_bypass_strategy_preparation():
    from Backend.domain.models.context import StrategyContext
    from Backend.domain.strategies.base import BaseStrategy

    class ProbeStrategy(BaseStrategy):
        def prepare_data(self, data):
            self.preparation_called = True
            return pd.DataFrame()

        def generate_signals(self, candles, context):
            return []

        def calculate_levels(self, candles, index, side, context):
            return (0.0, 0.0)

    strategy = ProbeStrategy()
    strategy.preparation_called = False

    external_frame = pd.DataFrame({
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.0],
    })

    context = StrategyContext(
        symbol="NIFTY",
        capital=100000,
        risk_pct=1.0,
        rr_ratio=2.0,
        params={"_backtest_prepared_frame": external_frame},
    )

    strategy.run(external_frame, context)

    assert strategy.preparation_called is True, (
        "External caller bypassed normal strategy preparation"
    )


def test_cache_authorization_isolated_between_threads():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def authorized_worker():
        with allow_backtest_cache():
            barrier.wait(timeout=10)
            return backtest_cache_allowed()

    def unauthorized_worker():
        barrier.wait(timeout=10)
        return backtest_cache_allowed()

    with ThreadPoolExecutor(max_workers=2) as executor:
        authorized = executor.submit(authorized_worker)
        unauthorized = executor.submit(unauthorized_worker)

        assert authorized.result(timeout=15) is True
        assert unauthorized.result(timeout=15) is False

    assert backtest_cache_allowed() is False
