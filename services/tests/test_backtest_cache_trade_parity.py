"""End-to-end breakout backtest parity with indicator caching."""

import contextlib
import io

import numpy as np
import pandas as pd

from Backend.trading_system.backtesting import BacktestEngine


def test_cached_backtest_matches_completed_trades():
    rng = np.random.default_rng(159)
    n = 260

    timestamps = pd.date_range(
        "2026-10-26 09:15",
        periods=n,
        freq="min",
        tz="Asia/Kolkata",
    )

    close = 23000 + np.cumsum(rng.normal(0, 8, n))

    candles = pd.DataFrame({
        "timestamp": timestamps,
        "open": close,
        "high": close + rng.uniform(3, 10, n),
        "low": close - rng.uniform(3, 10, n),
        "close": close,
        "volume": rng.integers(1000, 5000, n),
    })

    def execute(enabled):
        engine = BacktestEngine(
            commission_rate=0,
            slippage_rate=0,
            brokerage_per_order=0,
            brokerage_bps=0,
            taxes_bps=0,
        )

        with contextlib.redirect_stdout(io.StringIO()):
            return engine.run(
                candles=candles.copy(),
                strategy_name="breakout",
                symbol="NIFTY",
                capital=100000,
                risk_pct=1.0,
                rr_ratio=2.0,
                use_indicator_cache=enabled,
            )

    baseline = execute(False)
    cached = execute(True)

    assert baseline.total_trades == cached.total_trades
    assert baseline.total_trades >= 2

    for field in (
        "net_pnl",
        "win_rate",
        "max_drawdown",
        "profit_factor",
    ):
        assert np.isclose(
            getattr(baseline, field),
            getattr(cached, field),
            equal_nan=True,
        ), field

    assert len(baseline.trades) == len(cached.trades)

    for original, optimized in zip(
        baseline.trades, cached.trades
    ):
        original = {
            key: value
            for key, value in original.items()
            if key != "id"
        }

        optimized = {
            key: value
            for key, value in optimized.items()
            if key != "id"
        }

        assert original == optimized

    assert {trade["side"] for trade in baseline.trades} == {
        "BUY", "SELL"
    }
