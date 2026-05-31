from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd


Trend = Literal["UPTREND", "DOWNTREND", "RANGE"]


@dataclass(frozen=True, slots=True)
class TrendContext:
    trend: Trend
    higher_highs: bool
    higher_lows: bool
    lower_highs: bool
    lower_lows: bool
    structure_breaks: int

    @property
    def side(self) -> str | None:
        if self.trend == "UPTREND":
            return "BUY"
        if self.trend == "DOWNTREND":
            return "SELL"
        return None

    def to_dict(self) -> dict:
        return asdict(self)


class TrendAnalyzer:
    def analyze(self, candles: pd.DataFrame) -> TrendContext:
        if candles is None or len(candles) < 8:
            return TrendContext("RANGE", False, False, False, False, 0)
        recent = candles.tail(12)
        highs = recent["high"].astype(float)
        lows = recent["low"].astype(float)
        first_high = float(highs.iloc[: len(highs) // 2].max())
        last_high = float(highs.iloc[len(highs) // 2 :].max())
        first_low = float(lows.iloc[: len(lows) // 2].min())
        last_low = float(lows.iloc[len(lows) // 2 :].min())
        higher_highs = last_high > first_high
        higher_lows = last_low > first_low
        lower_highs = last_high < first_high
        lower_lows = last_low < first_low
        breaks = self._structure_breaks(recent)
        if higher_highs and higher_lows:
            trend: Trend = "UPTREND"
        elif lower_highs and lower_lows:
            trend = "DOWNTREND"
        else:
            trend = "RANGE"
        return TrendContext(trend, higher_highs, higher_lows, lower_highs, lower_lows, breaks)

    @staticmethod
    def _structure_breaks(candles: pd.DataFrame) -> int:
        if len(candles) < 4:
            return 0
        previous_high = candles["high"].shift(1).rolling(4, min_periods=2).max()
        previous_low = candles["low"].shift(1).rolling(4, min_periods=2).min()
        bull = candles["close"] > previous_high
        bear = candles["close"] < previous_low
        return int((bull.fillna(False) | bear.fillna(False)).sum())
