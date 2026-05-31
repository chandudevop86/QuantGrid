from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True, slots=True)
class TriggerResult:
    valid: bool
    trigger_type: str
    direction: str | None
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


class TriggerDetector:
    def detect(self, candles: pd.DataFrame, index: int, side: str) -> TriggerResult:
        if index < 4 or candles.empty:
            return TriggerResult(False, "none", None, 0.0)
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        window = candles.iloc[max(0, index - 8) : index]
        direction = side.upper()
        if self._bos(row, window, direction):
            return TriggerResult(True, "BOS", direction, 0.86)
        if self._choch(row, window, direction):
            return TriggerResult(True, "ChoCH", direction, 0.9)
        if self._engulfing(row, previous, direction):
            return TriggerResult(True, f"{direction.title()} Engulfing", direction, 0.82)
        if self._double(row, window, direction):
            return TriggerResult(True, "Double Bottom" if direction == "BUY" else "Double Top", direction, 0.76)
        if self._liquidity_sweep(row, window, direction):
            return TriggerResult(True, "Liquidity Sweep", direction, 0.88)
        if self._false_breakout(row, window, direction):
            return TriggerResult(True, "False Breakout", direction, 0.8)
        return TriggerResult(False, "none", None, 0.0)

    @staticmethod
    def _bos(row: pd.Series, window: pd.DataFrame, side: str) -> bool:
        if window.empty:
            return False
        return float(row["close"]) > float(window["high"].max()) if side == "BUY" else float(row["close"]) < float(window["low"].min())

    @staticmethod
    def _choch(row: pd.Series, window: pd.DataFrame, side: str) -> bool:
        if len(window) < 4:
            return False
        midpoint = (float(window["high"].max()) + float(window["low"].min())) / 2.0
        return float(row["close"]) > midpoint and float(row["open"]) < midpoint if side == "BUY" else float(row["close"]) < midpoint and float(row["open"]) > midpoint

    @staticmethod
    def _engulfing(row: pd.Series, previous: pd.Series, side: str) -> bool:
        if side == "BUY":
            return float(row["close"]) > float(row["open"]) and float(row["close"]) > float(previous["open"]) and float(row["open"]) <= float(previous["close"])
        return float(row["close"]) < float(row["open"]) and float(row["close"]) < float(previous["open"]) and float(row["open"]) >= float(previous["close"])

    @staticmethod
    def _double(row: pd.Series, window: pd.DataFrame, side: str) -> bool:
        if window.empty:
            return False
        tolerance = max(float(row.get("atr_14", 0.0) or 0.0) * 0.35, 0.01)
        if side == "BUY":
            return abs(float(row["low"]) - float(window["low"].min())) <= tolerance
        return abs(float(row["high"]) - float(window["high"].max())) <= tolerance

    @staticmethod
    def _liquidity_sweep(row: pd.Series, window: pd.DataFrame, side: str) -> bool:
        if window.empty:
            return False
        if side == "BUY":
            swept = float(row["low"]) < float(window["low"].min())
            return swept and float(row["close"]) > float(window["low"].min())
        swept = float(row["high"]) > float(window["high"].max())
        return swept and float(row["close"]) < float(window["high"].max())

    @staticmethod
    def _false_breakout(row: pd.Series, window: pd.DataFrame, side: str) -> bool:
        if window.empty:
            return False
        high = float(window["high"].max())
        low = float(window["low"].min())
        if side == "BUY":
            return float(row["low"]) < low and float(row["close"]) > low
        return float(row["high"]) > high and float(row["close"]) < high
