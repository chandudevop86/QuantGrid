from __future__ import annotations

import pandas as pd

from Backend.domain.breakout.models import Side


class BreakoutTrendFilter:
    def allowed_side(self, row: pd.Series) -> Side | None:
        ema50 = float(row["ema_50"])
        ema200 = float(row["ema_200"])
        if ema50 > ema200:
            return "BUY"
        if ema50 < ema200:
            return "SELL"
        return None

    def aligned(self, row: pd.Series, side: Side) -> bool:
        allowed = self.allowed_side(row)
        return allowed == side
