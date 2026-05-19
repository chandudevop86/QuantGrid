from __future__ import annotations

import pandas as pd

from Backend.domain.supply_demand.models import EntryConfirmation, SDZone, Side


class EntryConfirmationEngine:
    def confirm(self, candles: pd.DataFrame, index: int, side: Side, zone: SDZone) -> EntryConfirmation | None:
        if index < 1:
            return None
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        if not self._returned_to_zone(row, zone):
            return None
        if not self._at_zone_edge(row, zone, side):
            return None

        engulfing = self._engulfing(row, previous, side)
        rejection = self._rejection(row, side)
        if engulfing:
            return EntryConfirmation("engulfing", 2.0, "engulfing candle at fresh zone")
        if rejection:
            return EntryConfirmation("rejection", 1.5, "wick rejection at fresh zone")
        return None

    @staticmethod
    def _returned_to_zone(row: pd.Series, zone: SDZone) -> bool:
        return float(row["low"]) <= zone.high and float(row["high"]) >= zone.low

    @staticmethod
    def _at_zone_edge(row: pd.Series, zone: SDZone, side: Side) -> bool:
        if zone.width <= 0:
            return False
        close = float(row["close"])
        location = (close - zone.low) / zone.width
        if side == "BUY":
            return location >= 0.35
        return location <= 0.65

    @staticmethod
    def _rejection(row: pd.Series, side: Side) -> bool:
        bar_range = max(float(row["bar_range"]), 0.01)
        upper_wick = float(row["high"]) - max(float(row["open"]), float(row["close"]))
        lower_wick = min(float(row["open"]), float(row["close"])) - float(row["low"])
        if side == "BUY":
            return float(row["close"]) > float(row["open"]) and lower_wick >= bar_range * 0.35
        return float(row["close"]) < float(row["open"]) and upper_wick >= bar_range * 0.35

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
