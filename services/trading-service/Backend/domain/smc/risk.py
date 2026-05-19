from __future__ import annotations

import pandas as pd

from Backend.domain.smc.models import Side, SupplyDemandZone


class SMCRiskManager:
    def levels(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        zone: SupplyDemandZone,
        entry: float,
        min_rr: float = 2.0,
        ideal_rr: float = 3.0,
    ) -> tuple[float, float]:
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        buffer = max(atr * 0.25, float(entry) * 0.0005, 0.05)

        if side == "BUY":
            stop = min(zone.low, float(row["low"])) - buffer
            pool = self._next_buy_liquidity(candles, index, entry)
            min_target = entry + (entry - stop) * min_rr
            ideal_target = entry + (entry - stop) * ideal_rr
            target = pool if pool is not None and pool >= min_target else ideal_target
            return stop, target

        stop = max(zone.high, float(row["high"])) + buffer
        pool = self._next_sell_liquidity(candles, index, entry)
        min_target = entry - (stop - entry) * min_rr
        ideal_target = entry - (stop - entry) * ideal_rr
        target = pool if pool is not None and pool <= min_target else ideal_target
        return stop, target

    @staticmethod
    def _next_buy_liquidity(candles: pd.DataFrame, index: int, entry: float) -> float | None:
        future_or_recent = candles.iloc[max(0, index - 50) : index]
        highs = future_or_recent[future_or_recent["high"] > entry]["high"]
        return float(highs.max()) if not highs.empty else None

    @staticmethod
    def _next_sell_liquidity(candles: pd.DataFrame, index: int, entry: float) -> float | None:
        future_or_recent = candles.iloc[max(0, index - 50) : index]
        lows = future_or_recent[future_or_recent["low"] < entry]["low"]
        return float(lows.min()) if not lows.empty else None
