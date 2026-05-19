from __future__ import annotations

import pandas as pd

from Backend.domain.smc.models import LiquidityRange, LiquiditySweep, Side


class LiquiditySweepDetector:
    def __init__(self, *, equal_level_tolerance_atr: float = 0.20, min_equal_touches: int = 2) -> None:
        self.equal_level_tolerance_atr = float(equal_level_tolerance_atr)
        self.min_equal_touches = int(min_equal_touches)

    def detect_range(self, candles: pd.DataFrame, index: int, lookback: int) -> LiquidityRange | None:
        if index < max(4, lookback):
            return None
        start = max(0, index - lookback)
        window = candles.iloc[start:index]
        if window.empty:
            return None

        range_high = float(window["high"].max())
        range_low = float(window["low"].min())
        atr = float(candles.iloc[index].get("atr_14", candles.iloc[index].get("avg_range_5", 0.0)) or 0.0)
        tolerance = max(atr * self.equal_level_tolerance_atr, range_high * 0.0005, 0.01)
        equal_highs = int((window["high"].sub(range_high).abs() <= tolerance).sum())
        equal_lows = int((window["low"].sub(range_low).abs() <= tolerance).sum())
        width = range_high - range_low
        avg_range = float(window["bar_range"].mean() or 0.0)
        is_consolidating = width <= max(avg_range * 5.0, atr * 4.5, range_high * 0.015)
        if not is_consolidating:
            return None
        if equal_highs < self.min_equal_touches and equal_lows < self.min_equal_touches:
            return None
        return LiquidityRange(
            high=range_high,
            low=range_low,
            start_index=start,
            end_index=index - 1,
            equal_highs=equal_highs,
            equal_lows=equal_lows,
            atr=atr,
        )

    def detect_sweep(self, candles: pd.DataFrame, index: int, liquidity_range: LiquidityRange, side: Side) -> LiquiditySweep | None:
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", liquidity_range.atr) or liquidity_range.atr), 0.01)
        close = float(row["close"])

        if side == "SELL":
            wick_break = float(row["high"]) > liquidity_range.high
            close_returned = close < liquidity_range.high
            if not (wick_break and close_returned):
                return None
            wick_extension = float(row["high"]) - liquidity_range.high
            quality = min(3.0, 1.0 + wick_extension / atr + (1.0 if close < liquidity_range.midpoint else 0.0))
            return LiquiditySweep("SELL", liquidity_range.high, index, float(row["high"]), close, quality, "SELL")

        wick_break = float(row["low"]) < liquidity_range.low
        close_returned = close > liquidity_range.low
        if not (wick_break and close_returned):
            return None
        wick_extension = liquidity_range.low - float(row["low"])
        quality = min(3.0, 1.0 + wick_extension / atr + (1.0 if close > liquidity_range.midpoint else 0.0))
        return LiquiditySweep("BUY", liquidity_range.low, index, float(row["low"]), close, quality, "BUY")
