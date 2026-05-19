from __future__ import annotations

import pandas as pd

from Backend.domain.supply_demand.models import SDZone, Side
from Backend.domain.supply_demand.zones import ZoneDetectionEngine


class SDRiskManager:
    def __init__(self, zone_engine: ZoneDetectionEngine | None = None) -> None:
        self.zone_engine = zone_engine or ZoneDetectionEngine()

    def levels(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        zone: SDZone,
        entry: float,
        min_rr: float = 2.0,
    ) -> tuple[float, float]:
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        buffer = max(atr * 0.25, float(entry) * 0.0004, 0.05)
        if side == "BUY":
            stop = min(zone.low, float(row["low"])) - buffer
            rr_target = entry + (entry - stop) * min_rr
            opposing = self.zone_engine.opposing_zone_target(candles, index, side, entry)
            target = opposing if opposing is not None and opposing >= rr_target else rr_target
            return stop, target
        stop = max(zone.high, float(row["high"])) + buffer
        rr_target = entry - (stop - entry) * min_rr
        opposing = self.zone_engine.opposing_zone_target(candles, index, side, entry)
        target = opposing if opposing is not None and opposing <= rr_target else rr_target
        return stop, target
