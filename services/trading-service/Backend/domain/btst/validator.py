from __future__ import annotations

import pandas as pd

from Backend.domain.btst.models import GapAssessment, Side, SwingStructure


class BTSTSignalValidator:
    def __init__(self, *, min_atr_pct: float = 0.001, min_score: int = 6) -> None:
        self.min_atr_pct = float(min_atr_pct)
        self.min_score = int(min_score)

    def valid_market(self, row: pd.Series, structure: SwingStructure, side: Side) -> tuple[bool, str]:
        if structure.side != side or not structure.structure_confirmed or not structure.breakout_confirmed:
            return False, "structure or breakout not confirmed"
        atr_pct = float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0) / max(float(row["close"]), 0.01)
        if atr_pct < self.min_atr_pct:
            return False, "low volatility sideways day"
        return True, "accepted"

    def valid_signal(self, *, score: int, gap: GapAssessment) -> tuple[bool, str]:
        if score < self.min_score:
            return False, "score below threshold"
        if not gap.allowed:
            return False, "gap probability filter rejected setup"
        return True, "accepted"
