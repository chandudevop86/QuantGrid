from __future__ import annotations

import pandas as pd

from Backend.domain.btst.models import Side, SwingStructure


class SwingStructureDetector:
    def __init__(self, *, swing_window: int = 3) -> None:
        self.swing_window = int(swing_window)

    def detect(self, candles: pd.DataFrame, index: int) -> SwingStructure:
        frame = candles.iloc[: index + 1]
        if len(frame) < self.swing_window * 2 + 10:
            return SwingStructure("sideways", None, None, None, False, False, "not enough swing history")

        ema50 = float(frame.iloc[-1]["ema_50"])
        ema200 = float(frame.iloc[-1]["ema_200"])
        side: Side | None = "BUY" if ema50 > ema200 else "SELL" if ema50 < ema200 else None
        highs, lows = self._swings(frame)
        if len(highs) < 2 or len(lows) < 2 or side is None:
            return SwingStructure("sideways", side, highs[-1][1] if highs else None, lows[-1][1] if lows else None, False, False, "unclear swing structure")

        previous_high, last_high = highs[-2][1], highs[-1][1]
        previous_low, last_low = lows[-2][1], lows[-1][1]
        close = float(frame.iloc[-1]["close"])

        if side == "BUY":
            structure_ok = last_high > previous_high and last_low > previous_low
            breakout = close > last_high
            return SwingStructure(
                "bullish" if structure_ok else "sideways",
                side,
                last_high,
                last_low,
                breakout,
                structure_ok,
                "HH/HL with previous swing-high breakout" if structure_ok and breakout else "bullish EMA without confirmed HH/HL breakout",
            )

        structure_ok = last_high < previous_high and last_low < previous_low
        breakdown = close < last_low
        return SwingStructure(
            "bearish" if structure_ok else "sideways",
            side,
            last_high,
            last_low,
            breakdown,
            structure_ok,
            "LH/LL with previous swing-low breakdown" if structure_ok and breakdown else "bearish EMA without confirmed LH/LL breakdown",
        )

    def _swings(self, frame: pd.DataFrame) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
        highs: list[tuple[int, float]] = []
        lows: list[tuple[int, float]] = []
        for index in range(self.swing_window, len(frame) - self.swing_window):
            window = frame.iloc[index - self.swing_window : index + self.swing_window + 1]
            row = frame.iloc[index]
            if float(row["high"]) >= float(window["high"].max()):
                highs.append((index, float(row["high"])))
            if float(row["low"]) <= float(window["low"].min()):
                lows.append((index, float(row["low"])))
        return highs, lows
