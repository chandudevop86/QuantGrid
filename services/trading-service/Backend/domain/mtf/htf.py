from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.mtf.models import HTFTrend


class HTFTrendAnalyzer:
    def __init__(self, indicators: IndicatorService | None = None, *, swing_window: int = 3) -> None:
        self.indicators = indicators or IndicatorService()
        self.swing_window = int(swing_window)

    def prepare(self, data: Any | None) -> pd.DataFrame | None:
        if data is None:
            return None
        prepared = self.indicators.prepare(data)
        return prepared if not prepared.empty else None

    def analyze_at(self, htf_candles: pd.DataFrame | None, ltf_row: pd.Series) -> HTFTrend:
        row, frame = self._context(htf_candles, ltf_row)
        ema50 = float(row["ema_50"])
        ema200 = float(row["ema_200"])
        structure_bias, structure_level = self._structure(frame)

        if ema50 > ema200 and structure_bias == "bullish":
            return HTFTrend("bullish", True, True, abs(ema50 - ema200) / max(float(row["close"]), 1.0), structure_level, "HTF EMA50>EMA200 with HH/HL structure")
        if ema50 < ema200 and structure_bias == "bearish":
            return HTFTrend("bearish", True, True, abs(ema50 - ema200) / max(float(row["close"]), 1.0), structure_level, "HTF EMA50<EMA200 with LH/LL structure")
        if ema50 > ema200:
            return HTFTrend("sideways", True, False, 0.0, structure_level, "HTF EMA bullish but structure unclear")
        if ema50 < ema200:
            return HTFTrend("sideways", True, False, 0.0, structure_level, "HTF EMA bearish but structure unclear")
        return HTFTrend("sideways", False, False, 0.0, None, "HTF trend is sideways")

    def _context(self, htf_candles: pd.DataFrame | None, ltf_row: pd.Series) -> tuple[pd.Series, pd.DataFrame]:
        if htf_candles is None or htf_candles.empty:
            return ltf_row, pd.DataFrame([ltf_row])
        timestamp = pd.Timestamp(ltf_row["timestamp"])
        frame = htf_candles[htf_candles["timestamp"] <= timestamp]
        if frame.empty:
            frame = htf_candles.iloc[:1]
        return frame.iloc[-1], frame

    def _structure(self, frame: pd.DataFrame) -> tuple[str, float | None]:
        if len(frame) < self.swing_window * 2 + 5:
            return "sideways", None
        swings_high: list[tuple[int, float]] = []
        swings_low: list[tuple[int, float]] = []
        for index in range(self.swing_window, len(frame) - self.swing_window):
            window = frame.iloc[index - self.swing_window : index + self.swing_window + 1]
            row = frame.iloc[index]
            if float(row["high"]) >= float(window["high"].max()):
                swings_high.append((index, float(row["high"])))
            if float(row["low"]) <= float(window["low"].min()):
                swings_low.append((index, float(row["low"])))
        if len(swings_high) < 2 or len(swings_low) < 2:
            return "sideways", None
        last_highs = swings_high[-2:]
        last_lows = swings_low[-2:]
        higher_high = last_highs[-1][1] > last_highs[-2][1]
        higher_low = last_lows[-1][1] > last_lows[-2][1]
        lower_high = last_highs[-1][1] < last_highs[-2][1]
        lower_low = last_lows[-1][1] < last_lows[-2][1]
        if higher_high and higher_low:
            return "bullish", last_highs[-1][1]
        if lower_high and lower_low:
            return "bearish", last_lows[-1][1]
        return "sideways", None
