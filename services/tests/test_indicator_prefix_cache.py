"""Parity tests for experimental backtest indicator reuse."""

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from Backend.domain.indicators.indicators import IndicatorService
from Backend.trading_system.indicator_prefix_cache import IndicatorPrefixCache


def test_indicator_prefix_cache_matches_original():
    rng = np.random.default_rng(157)
    n = 240
    close = 23000 + np.cumsum(rng.normal(0, 12, n))

    candles = pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-10-26 09:15",
            periods=n,
            freq="min",
            tz="Asia/Kolkata",
        ),
        "open": close,
        "high": close + rng.uniform(5, 15, n),
        "low": close - rng.uniform(5, 15, n),
        "close": close,
        "volume": rng.integers(1000, 5000, n),
    })

    cache = IndicatorPrefixCache(candles)
    service = IndicatorService()

    for end in range(1, n + 1):
        expected = service.prepare(candles.iloc[:end])
        actual = cache.prefix(end)

        assert_frame_equal(
            actual,
            expected,
            check_exact=False,
            rtol=1e-9,
            atol=1e-9,
            obj=f"Historical prefix {end}",
        )


def test_indicator_prefix_cache_irregular_market_data():
    rng = np.random.default_rng(158)

    timestamps = (
        list(pd.date_range(
            "2026-10-26 09:15",
            periods=75,
            freq="min",
            tz="Asia/Kolkata",
        ))
        +
        list(pd.date_range(
            "2026-10-27 09:15",
            periods=75,
            freq="min",
            tz="Asia/Kolkata",
        ))
    )

    # Missing candles and one repeated timestamp.
    timestamps = [
        timestamp for index, timestamp in enumerate(timestamps)
        if index not in {12, 35, 91}
    ]
    timestamps.insert(40, timestamps[39])

    n = len(timestamps)
    close = 23000 + np.cumsum(rng.normal(0, 15, n))

    candles = pd.DataFrame({
        "timestamp": timestamps,
        "open": close,
        "high": close + rng.uniform(5, 15, n),
        "low": close - rng.uniform(5, 15, n),
        "close": close,
        "volume": rng.integers(1000, 5000, n),
    })

    service = IndicatorService()
    cache = IndicatorPrefixCache(candles)

    for end in range(1, n + 1):
        expected = service.prepare(candles.iloc[:end])
        actual = cache.prefix(end)

        assert_frame_equal(
            actual,
            expected,
            check_exact=False,
            rtol=1e-9,
            atol=1e-9,
            obj=f"Irregular market prefix {end}",
        )
