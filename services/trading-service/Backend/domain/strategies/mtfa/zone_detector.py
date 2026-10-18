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
    direction: Literal["BUY", "SELL"] | None = None

    def aligns(self, side: str) -> bool:
        side = side.upper()
        if self.zone_type in {"order_block", "fair_value_gap"}:
            return self.direction == side
        if side == "BUY":
            return self.zone_type in {"support", "demand"}
        return self.zone_type in {"resistance", "supply"}

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
        for side in ("BUY", "SELL"):
            block = self._order_block(recent, atr, side)
            if block is not None:
                zones.append(block)
            gap = self._fair_value_gap(recent, atr, side)
            if gap is not None:
                zones.append(gap)
        return zones

    def best_for_side(self, candles: pd.DataFrame, side: str) -> MTFAZone | None:
        aligned = [zone for zone in self.detect(candles) if zone.aligns(side)]
        if not aligned:
            return None
        return max(aligned, key=lambda zone: zone.strength)

    @staticmethod
    def _order_block(candles: pd.DataFrame, atr: float, side: str) -> MTFAZone | None:
        """Last opposite candle preceding displacement through prior structure."""
        if len(candles) < 10:
            return None
        bodies = (candles["close"] - candles["open"]).abs()
        min_body = max(float(bodies.tail(20).median()) * 1.2, atr * 0.6, 0.01)
        for i in range(len(candles) - 2, 7, -1):
            origin = candles.iloc[i]
            opposite = (
                float(origin["close"]) < float(origin["open"])
                if side == "BUY" else float(origin["close"]) > float(origin["open"])
            )
            if not opposite:
                continue
            preceding = candles.iloc[max(0, i - 8):i]
            if len(preceding) < 5:
                continue
            prior_high = float(preceding["high"].max())
            prior_low = float(preceding["low"].min())
            for j in range(i + 1, min(i + 4, len(candles))):
                impulse = candles.iloc[j]
                body = abs(float(impulse["close"]) - float(impulse["open"]))
                if body < min_body:
                    continue
                impulse_bullish = float(impulse["close"]) > float(impulse["open"])
                if impulse_bullish != (side == "BUY"):
                    continue
                if side == "BUY":
                    confirmed = float(impulse["close"]) > prior_high + atr * 0.05
                else:
                    confirmed = float(impulse["close"]) < prior_low - atr * 0.05
                if confirmed:
                    return MTFAZone("order_block", float(origin["high"]), float(origin["low"]), 2.0, side)
        return None

    @staticmethod
    def _fair_value_gap(candles: pd.DataFrame, atr: float, side: str) -> MTFAZone | None:
        """Three-candle gap large enough to matter and not fully filled."""
        if len(candles) < 3:
            return None
        for i in range(len(candles) - 1, 1, -1):
            first = candles.iloc[i - 2]
            third = candles.iloc[i]
            if side == "BUY":
                low, high = float(first["high"]), float(third["low"])
            else:
                low, high = float(third["high"]), float(first["low"])
            if high - low < max(atr * 0.10, 0.01):
                continue
            later = candles.iloc[i + 1:]
            if not later.empty:
                filled = (
                    (later["low"].astype(float) <= low).any()
                    if side == "BUY" else (later["high"].astype(float) >= high).any()
                )
                if filled:
                    continue
            return MTFAZone("fair_value_gap", high, low, 1.5, side)
        return None
