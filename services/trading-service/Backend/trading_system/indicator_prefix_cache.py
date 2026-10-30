"""Experimental backtest-scoped indicator prefix cache.

Preserves original per-prefix OHLCV normalization semantics.
Not connected to production or live trading.
"""

from __future__ import annotations

import pandas as pd

from Backend.domain.indicators.indicators import (
    IndicatorService,
    prepare_ohlcv,
)


class IndicatorPrefixCache:
    """Cache indicator preparation with a safe normalization fallback."""

    def __init__(self, candles):
        self._raw = pd.DataFrame(candles).copy()
        self._service = IndicatorService()

        normalized = prepare_ohlcv(self._raw)

        # Precomputation is enabled only if normalization preserves
        # the original row count, order, and timestamps.
        raw_timestamps = pd.to_datetime(
            self._raw["timestamp"], utc=True
        ).reset_index(drop=True)

        normalized_timestamps = pd.to_datetime(
            normalized["timestamp"], utc=True
        ).reset_index(drop=True)

        self._cache_enabled = (
            len(normalized) == len(self._raw)
            and raw_timestamps.equals(normalized_timestamps)
        )

        self._prepared = (
            self._service.prepare(self._raw)
            if self._cache_enabled
            else None
        )

    @property
    def cache_enabled(self) -> bool:
        return self._cache_enabled

    def prefix(self, end: int) -> pd.DataFrame:
        if not 0 <= end <= len(self._raw):
            raise ValueError("Prefix length is outside the candle dataset")

        if not self._cache_enabled:
            # Exact original calculation for irregular datasets.
            return self._service.prepare(self._raw.iloc[:end])

        result = self._prepared.iloc[:end].copy()

        # Centered five-bar swings require two future candles.
        # The final two candles are unconfirmed at this cutoff.
        if end:
            result.loc[
                result.index[-2:],
                ["swing_high", "swing_low"],
            ] = False

        return result
