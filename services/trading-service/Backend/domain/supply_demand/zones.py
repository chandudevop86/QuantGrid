from __future__ import annotations

import pandas as pd

from Backend.domain.supply_demand.models import SDZone, Side


class ZoneDetectionEngine:
    def __init__(
        self,
        *,
        lookback: int = 90,
        max_base_candles: int = 5,
        base_range_atr: float = 0.85,
        impulse_body_atr: float = 1.25,
        impulse_range_atr: float = 1.5,
        max_touches: int = 1,
    ) -> None:
        self.lookback = int(lookback)
        self.max_base_candles = int(max_base_candles)
        self.base_range_atr = float(base_range_atr)
        self.impulse_body_atr = float(impulse_body_atr)
        self.impulse_range_atr = float(impulse_range_atr)
        self.max_touches = int(max_touches)

    def detect_zones(self, candles: pd.DataFrame, index: int) -> list[SDZone]:
        start = max(self.max_base_candles + 1, index - self.lookback)
        zones: list[SDZone] = []
        for impulse_index in range(start, index):
            side = self._impulse_side(candles, impulse_index)
            if side is None:
                continue
            base = self._base_window(candles, impulse_index)
            if base is None:
                continue
            base_start, base_end = base
            window = candles.iloc[base_start : base_end + 1]
            zone = SDZone(
                zone_type="demand" if side == "BUY" else "supply",
                low=float(window["low"].min()),
                high=float(window["high"].max()),
                base_start=base_start,
                base_end=base_end,
                impulse_index=impulse_index,
                impulse_strength=self._impulse_strength(candles, impulse_index),
            )
            zone.touches = self.count_touches(candles, zone, impulse_index + 1, index - 1)
            if zone.touches <= self.max_touches:
                zones.append(zone)
        return sorted(zones, key=lambda item: (item.touches, -item.impulse_strength, -item.impulse_index))

    def zones_for_return(self, candles: pd.DataFrame, index: int, side: Side) -> list[SDZone]:
        current = candles.iloc[index]
        zones = [
            zone
            for zone in self.detect_zones(candles, index)
            if zone.side == side and float(current["low"]) <= zone.high and float(current["high"]) >= zone.low
        ]
        return zones

    def opposing_zone_target(self, candles: pd.DataFrame, index: int, side: Side, entry: float) -> float | None:
        opposing_side: Side = "SELL" if side == "BUY" else "BUY"
        zones = [zone for zone in self.detect_zones(candles, index) if zone.side == opposing_side]
        if side == "BUY":
            candidates = [zone.low for zone in zones if zone.low > entry]
            return float(min(candidates)) if candidates else None
        candidates = [zone.high for zone in zones if zone.high < entry]
        return float(max(candidates)) if candidates else None

    def count_touches(self, candles: pd.DataFrame, zone: SDZone, start: int, end: int) -> int:
        if end < start:
            return 0
        touches = 0
        in_zone = False
        for _, row in candles.iloc[start : end + 1].iterrows():
            overlaps = float(row["low"]) <= zone.high and float(row["high"]) >= zone.low
            if overlaps and not in_zone:
                touches += 1
            in_zone = overlaps
        return touches

    def _impulse_side(self, candles: pd.DataFrame, index: int) -> Side | None:
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        body = abs(float(row["close"]) - float(row["open"]))
        bar_range = float(row["bar_range"])
        if body < atr * self.impulse_body_atr or bar_range < atr * self.impulse_range_atr:
            return None
        if float(row["close"]) > float(row["open"]):
            return "BUY"
        if float(row["close"]) < float(row["open"]):
            return "SELL"
        return None

    def _base_window(self, candles: pd.DataFrame, impulse_index: int) -> tuple[int, int] | None:
        base_end = impulse_index - 1
        if base_end < 1:
            return None
        base_start = base_end
        while base_start - 1 >= 0 and base_end - base_start + 1 < self.max_base_candles:
            row = candles.iloc[base_start - 1]
            atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
            if float(row["bar_range"]) > atr * self.base_range_atr:
                break
            base_start -= 1
        window = candles.iloc[base_start : base_end + 1]
        if window.empty:
            return None
        avg_atr = max(float(window.get("atr_14", window["avg_range_5"]).mean() or 0.0), 0.01)
        if float(window["bar_range"].mean()) > avg_atr * self.base_range_atr:
            return None
        return base_start, base_end

    @staticmethod
    def _impulse_strength(candles: pd.DataFrame, index: int) -> float:
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        body = abs(float(row["close"]) - float(row["open"]))
        return body / atr
