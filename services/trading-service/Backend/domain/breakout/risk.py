from __future__ import annotations

import pandas as pd

from Backend.domain.breakout.models import BreakoutSetup, Side


class BreakoutRiskManager:
    def levels(self, row: pd.Series, setup: BreakoutSetup, *, min_rr: float = 2.0, atr_extension: float = 1.5) -> tuple[float, float]:
        close = float(row["close"])
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        buffer = max(atr * 0.15, close * 0.0003, 0.03)
        if setup.side == "BUY":
            stop = float(row["low"]) - buffer
            rr_target = close + (close - stop) * min_rr
            atr_target = close + atr * atr_extension
            return stop, max(rr_target, atr_target)
        stop = float(row["high"]) + buffer
        rr_target = close - (stop - close) * min_rr
        atr_target = close - atr * atr_extension
        return stop, min(rr_target, atr_target)
