from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd


ZoneType = Literal["support", "resistance", "supply", "demand", "order_block", "fair_value_gap"]


@dataclass(frozen=True, slots=True)
class MTFAZone:
    zone_type: ZoneType
    high: float
    low: float
    strength: float

    def aligns(self, side: str) -> bool:
        if side.upper() == "BUY":
            return self.zone_type in {"support", "demand", "order_block", "fair_value_gap"}
        return self.zone_type in {"resistance", "supply", "order_block", "fair_value_gap"}

    def contains(self, price: float, buffer: float = 0.0) -> bool:
        return float(self.low) - buffer <= float(price) <= float(self.high) + buffer

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["high"] = round(float(self.high), 4)
        payload["low"] = round(float(self.low), 4)
        payload["strength"] = round(float(self.strength), 2)
        return payload


class ZoneDetector:
    def detect(self, candles: pd.DataFrame) -> list[MTFAZone]:
        if candles is None or len(candles) < 6:
            return []
        recent = candles.tail(40)
        atr = max(float(recent["atr_14"].iloc[-1] or 0.0), float(recent["bar_range"].mean() or 0.0), 0.01)
        support = float(recent["low"].min())
        resistance = float(recent["high"].max())
        zones = [
            MTFAZone("support", support + atr * 0.35, support, 2.0),
            MTFAZone("resistance", resistance, resistance - atr * 0.35, 2.0),
            MTFAZone("demand", support + atr, support, 2.5),
            MTFAZone("supply", resistance, resistance - atr, 2.5),
        ]
        order_block = self._order_block(recent, atr)
        if order_block is not None:
            zones.append(order_block)
        fvg = self._fair_value_gap(recent)
        if fvg is not None:
            zones.append(fvg)
        return zones

    def best_for_side(self, candles: pd.DataFrame, side: str) -> MTFAZone | None:
        aligned = [zone for zone in self.detect(candles) if zone.aligns(side)]
        if not aligned:
            return None
        return max(aligned, key=lambda zone: zone.strength)

    @staticmethod
    def _order_block(candles: pd.DataFrame, atr: float) -> MTFAZone | None:
        body = (candles["close"] - candles["open"]).abs()
        candidates = candles[body >= max(atr * 0.6, 0.01)]
        if candidates.empty:
            return None
        row = candidates.iloc[-1]
        return MTFAZone("order_block", float(row["high"]), float(row["low"]), 2.0)

    @staticmethod
    def _fair_value_gap(candles: pd.DataFrame) -> MTFAZone | None:
        if len(candles) < 3:
            return None
        for index in range(len(candles) - 1, 1, -1):
            row = candles.iloc[index]
            two_back = candles.iloc[index - 2]
            if float(row["low"]) > float(two_back["high"]):
                return MTFAZone("fair_value_gap", float(row["low"]), float(two_back["high"]), 1.5)
            if float(row["high"]) < float(two_back["low"]):
                return MTFAZone("fair_value_gap", float(two_back["low"]), float(row["high"]), 1.5)
        return None
