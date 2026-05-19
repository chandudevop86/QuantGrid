from __future__ import annotations

import pandas as pd

from Backend.domain.smc.models import FVGZone, Side


class FVGDetector:
    def __init__(self, *, min_gap_atr: float = 0.10, max_age_bars: int = 12) -> None:
        self.min_gap_atr = float(min_gap_atr)
        self.max_age_bars = int(max_age_bars)

    def find_active_return(self, candles: pd.DataFrame, index: int, side: Side, *, after_index: int) -> FVGZone | None:
        left = max(after_index + 2, index - self.max_age_bars)
        for created_index in range(index - 1, left - 1, -1):
            zone = self.detect_at(candles, created_index, side)
            if zone is None:
                continue
            if self._price_returns_to_zone(candles.iloc[index], zone):
                zone.mitigated_index = index
                return zone
        return None

    def detect_at(self, candles: pd.DataFrame, index: int, side: Side) -> FVGZone | None:
        if index < 2:
            return None
        candle1 = candles.iloc[index - 2]
        candle3 = candles.iloc[index]
        atr = max(float(candle3.get("atr_14", candle3.get("avg_range_5", 0.0)) or 0.0), 0.01)

        if side == "BUY" and float(candle1["high"]) < float(candle3["low"]):
            low = float(candle1["high"])
            high = float(candle3["low"])
            if high - low >= atr * self.min_gap_atr:
                return FVGZone(side="BUY", low=low, high=high, created_index=index)

        if side == "SELL" and float(candle1["low"]) > float(candle3["high"]):
            low = float(candle3["high"])
            high = float(candle1["low"])
            if high - low >= atr * self.min_gap_atr:
                return FVGZone(side="SELL", low=low, high=high, created_index=index)
        return None

    @staticmethod
    def _price_returns_to_zone(row: pd.Series, zone: FVGZone) -> bool:
        return float(row["low"]) <= zone.high and float(row["high"]) >= zone.low
