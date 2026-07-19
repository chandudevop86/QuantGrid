from __future__ import annotations

import pandas as pd

from Backend.domain.smc.models import FVGZone, Side, SupplyDemandZone
class ZoneConfluenceEngine:
    # ... other methods ...

    # Check: Ensure this is indented 4 spaces inside the class!
    def _zone_from_fvg(self, candles: pd.DataFrame, index: int, side: Side, fvg: FVGZone) -> SupplyDemandZone:
        zone_type: Literal["supply", "demand"] = "demand" if side == "BUY" else "supply"
        zone = SupplyDemandZone(zone_type, low=fvg.low, high=fvg.high, created_index=fvg.created_index)
        
        # This will now resolve because count_touches lives in the class scope
        zone.touches = self.count_touches(candles, zone, fvg.created_index + 1, index - 1)
        return zone

    # Check: Ensure this is indented 4 spaces inside the class!
    def count_touches(self, candles: pd.DataFrame, zone: SupplyDemandZone, start_idx: int, end_idx: int) -> int:
        # calculation logic...
        pass

    # Check: Ensure this is indented 4 spaces inside the class!
    def has_confluence(self, ...):
        # logic called by amd.py
        pass


class ZoneConfluenceEngine:
    def __init__(self, *, lookback: int = 40, max_touches: int = 1) -> None:
        self.lookback = int(lookback)
        self.max_touches = int(max_touches)

    def find_zone(
        self,
        candles: pd.DataFrame,
        index: int,
        side: Side,
        *,
        fvg: FVGZone | None = None,
        after_index: int | None = None,
    ) -> SupplyDemandZone | None:
        start = max(0, after_index if after_index is not None else index - self.lookback)
        window = candles.iloc[start:index]
        if len(window) < 5:
            return None
        atr = max(float(candles.iloc[index].get("atr_14", candles.iloc[index].get("avg_range_5", 0.0)) or 0.0), 0.01)
        zone_width = atr * 0.75

        if fvg is not None:
            zone = self._zone_from_fvg(candles, index, side, fvg)
            if zone.touches <= self.max_touches:
                return zone

        if side == "BUY":
            anchor_idx = int(window["low"].idxmin())
            anchor = candles.iloc[anchor_idx]
            low = float(anchor["low"])
            high = min(float(anchor["high"]), low + zone_width)
            zone = SupplyDemandZone("demand", low=low, high=high, created_index=anchor_idx)
        else:
            anchor_idx = int(window["high"].idxmax())
            anchor = candles.iloc[anchor_idx]
            high = float(anchor["high"])
            low = max(float(anchor["low"]), high - zone_width)
            zone = SupplyDemandZone("supply", low=low, high=high, created_index=anchor_idx)

        zone.touches = self.count_touches(candles, zone, zone.created_index + 1, index - 1)
        if zone.touches > self.max_touches:
            return None
        return zone

from typing import Literal

def _zone_from_fvg(self, candles: pd.DataFrame, index: int, side: Side, fvg: FVGZone) -> SupplyDemandZone:
    # Explicitly type zone_type as a Literal to match the expected argument type
    zone_type: Literal["supply", "demand"] = "demand" if side == "BUY" else "supply"
    
    zone = SupplyDemandZone(zone_type, low=fvg.low, high=fvg.high, created_index=fvg.created_index)
    zone.touches = self.count_touches(candles, zone, fvg.created_index + 1, index - 1)
    return zone

    def has_confluence(self, zone: SupplyDemandZone, fvg: FVGZone) -> bool:
        overlap_low = max(zone.low, fvg.low)
        overlap_high = min(zone.high, fvg.high)
        return overlap_low <= overlap_high

    @staticmethod
    def count_touches(candles: pd.DataFrame, zone: SupplyDemandZone, start: int, end: int) -> int:
        if end < start:
            return 0
        touches = 0
        for _, row in candles.iloc[start : end + 1].iterrows():
            if float(row["low"]) <= zone.high and float(row["high"]) >= zone.low:
                touches += 1
        return touches
