from __future__ import annotations

import pandas as pd

from Backend.domain.supply_demand.models import LiquidityEvent, SDZone, Side


class SDLiquidityDetector:
    def __init__(self, *, lookback: int = 24, equal_tolerance_atr: float = 0.20) -> None:
        self.lookback = int(lookback)
        self.equal_tolerance_atr = float(equal_tolerance_atr)

    def detect_near_zone(self, candles: pd.DataFrame, index: int, side: Side, zone: SDZone) -> LiquidityEvent | None:
        start = max(0, index - self.lookback)
        window = candles.iloc[start:index]
        if len(window) < 5:
            return None
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        tolerance = max(atr * self.equal_tolerance_atr, float(row["close"]) * 0.0004, 0.01)

        if side == "BUY":
            equal_low = float(window["low"].min())
            equal_count = int((window["low"].sub(equal_low).abs() <= tolerance).sum())
            swept = float(row["low"]) < min(equal_low, zone.low + tolerance) and float(row["close"]) > equal_low
            if equal_count >= 2 and swept:
                quality = 2.0 if float(row["close"]) > zone.midpoint else 1.0
                return LiquidityEvent("BUY", equal_low, index, quality, "equal lows swept and reclaimed")
        else:
            equal_high = float(window["high"].max())
            equal_count = int((window["high"].sub(equal_high).abs() <= tolerance).sum())
            swept = float(row["high"]) > max(equal_high, zone.high - tolerance) and float(row["close"]) < equal_high
            if equal_count >= 2 and swept:
                quality = 2.0 if float(row["close"]) < zone.midpoint else 1.0
                return LiquidityEvent("SELL", equal_high, index, quality, "equal highs swept and rejected")
        return None
