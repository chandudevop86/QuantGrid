from __future__ import annotations

import pandas as pd

from Backend.domain.breakout.models import BreakoutRange, BreakoutSetup, Side


class BreakoutDetectionEngine:
    def __init__(self, *, lookback: int = 20, max_expansion_atr: float = 1.5) -> None:
        self.lookback = int(lookback)
        self.max_expansion_atr = float(max_expansion_atr)

    def range_at(self, candles: pd.DataFrame, index: int) -> BreakoutRange | None:
        if index < self.lookback:
            return None
        start = index - self.lookback
        window = candles.iloc[start:index]
        if window.empty:
            return None
        high = float(window["high"].max())
        low = float(window["low"].min())
        atr = max(float(candles.iloc[index].get("atr_14", candles.iloc[index].get("avg_range_5", 0.0)) or 0.0), 0.01)
        return BreakoutRange(high=high, low=low, start_index=start, end_index=index - 1, size=high - low, atr=atr)

    def detect(self, candles: pd.DataFrame, index: int, side: Side) -> BreakoutSetup | None:
        breakout_range = self.range_at(candles, index)
        if breakout_range is None or breakout_range.size < breakout_range.atr:
            return None
        row = candles.iloc[index]
        close = float(row["close"])
        candle_range_atr = float(row["bar_range"]) / max(breakout_range.atr, 0.01)
        if candle_range_atr > self.max_expansion_atr:
            return None

        if side == "BUY":
            if close <= breakout_range.high:
                return None
            distance = close - breakout_range.high
            return BreakoutSetup(side, breakout_range, close, distance, candle_range_atr, "close-confirmed range high breakout")

        if close >= breakout_range.low:
            return None
        distance = breakout_range.low - close
        return BreakoutSetup(side, breakout_range, close, distance, candle_range_atr, "close-confirmed range low breakdown")
