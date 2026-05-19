from __future__ import annotations

import pandas as pd

from Backend.domain.mtf.models import LTFEntry, Side


class LTFEntryConfirmation:
    def confirm(self, candles: pd.DataFrame, index: int, side: Side) -> LTFEntry | None:
        if index < 1:
            return None
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        if not self._vwap_ok(row, side) or not self._rsi_ok(candles, index, side):
            return None
        engulfing = self._engulfing(row, previous, side)
        rejection = self._rejection(row, side)
        if engulfing:
            return LTFEntry(side, "engulfing", True, True, 2.0, "1m engulfing candle with RSI/VWAP confirmation")
        if rejection:
            return LTFEntry(side, "rejection", True, True, 1.5, "1m rejection candle with RSI/VWAP confirmation")
        return None

    @staticmethod
    def _vwap_ok(row: pd.Series, side: Side) -> bool:
        return float(row["close"]) >= float(row["vwap"]) if side == "BUY" else float(row["close"]) <= float(row["vwap"])

    @staticmethod
    def _rsi_ok(candles: pd.DataFrame, index: int, side: Side) -> bool:
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        if side == "BUY":
            return float(row["rsi"]) > 40.0 and float(row["rsi"]) > float(previous["rsi"])
        return float(row["rsi"]) < 60.0 and float(row["rsi"]) < float(previous["rsi"])

    @staticmethod
    def _engulfing(row: pd.Series, previous: pd.Series, side: Side) -> bool:
        if side == "BUY":
            return (
                float(row["close"]) > float(row["open"])
                and float(previous["close"]) < float(previous["open"])
                and float(row["close"]) >= float(previous["open"])
                and float(row["open"]) <= float(previous["close"])
            )
        return (
            float(row["close"]) < float(row["open"])
            and float(previous["close"]) > float(previous["open"])
            and float(row["close"]) <= float(previous["open"])
            and float(row["open"]) >= float(previous["close"])
        )

    @staticmethod
    def _rejection(row: pd.Series, side: Side) -> bool:
        bar_range = max(float(row["bar_range"]), 0.01)
        upper_wick = float(row["high"]) - max(float(row["open"]), float(row["close"]))
        lower_wick = min(float(row["open"]), float(row["close"])) - float(row["low"])
        if side == "BUY":
            return float(row["close"]) > float(row["open"]) and lower_wick >= bar_range * 0.35
        return float(row["close"]) < float(row["open"]) and upper_wick >= bar_range * 0.35
