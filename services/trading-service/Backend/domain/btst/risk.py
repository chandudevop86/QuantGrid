from __future__ import annotations

import pandas as pd

from Backend.domain.btst.models import EODConfirmation, Side, SwingStructure


class BTSTRiskManager:
    def levels(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        entry: float,
        eod: EODConfirmation,
        structure: SwingStructure,
        min_rr: float = 2.0,
    ) -> tuple[float, float]:
        row = candles.iloc[index]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        buffer = max(atr * 0.25, float(entry) * 0.0005, 0.05)
        if side == "BUY":
            stop = eod.day_low - buffer
            rr_target = entry + (entry - stop) * min_rr
            structure_target = structure.previous_swing_high
            target = structure_target if structure_target is not None and structure_target > rr_target else rr_target
            return stop, target
        stop = eod.day_high + buffer
        rr_target = entry - (stop - entry) * min_rr
        structure_target = structure.previous_swing_low
        target = structure_target if structure_target is not None and structure_target < rr_target else rr_target
        return stop, target
