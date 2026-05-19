from __future__ import annotations

import pandas as pd

from Backend.domain.mtf.models import HTFTrend, Side


class MTFRiskManager:
    def levels(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        entry: float,
        htf: HTFTrend,
        min_rr: float = 2.0,
        swing_lookback: int = 12,
    ) -> tuple[float, float]:
        start = max(0, index - swing_lookback)
        window = candles.iloc[start : index + 1]
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        buffer = max(atr * 0.25, float(entry) * 0.0004, 0.05)

        if side == "BUY":
            stop = float(window["low"].min()) - buffer
            rr_target = entry + (entry - stop) * min_rr
            target = htf.structure_level if htf.structure_level is not None and htf.structure_level > rr_target else rr_target
            return stop, target

        stop = float(window["high"].max()) + buffer
        rr_target = entry - (stop - entry) * min_rr
        target = htf.structure_level if htf.structure_level is not None and htf.structure_level < rr_target else rr_target
        return stop, target
