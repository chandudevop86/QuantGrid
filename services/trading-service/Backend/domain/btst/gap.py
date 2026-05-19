from __future__ import annotations

import pandas as pd

from Backend.domain.btst.models import EODConfirmation, GapAssessment, Side, SwingStructure


class GapProbabilityFilter:
    def __init__(self, *, min_probability_score: float = 0.65) -> None:
        self.min_probability_score = float(min_probability_score)

    def assess(self, row: pd.Series, *, side: Side, structure: SwingStructure, eod: EODConfirmation) -> GapAssessment:
        body_ratio = float(row["body_size"]) / max(float(row["bar_range"]), 0.01)
        trend_score = 0.35 if structure.structure_confirmed and structure.breakout_confirmed else 0.0
        close_score = 0.35 * eod.close_strength
        body_score = 0.20 if body_ratio >= 0.55 else 0.10 if body_ratio >= 0.35 else 0.0
        momentum_score = 0.10 if self._macd_supports(row, side) else 0.0
        score = trend_score + close_score + body_score + momentum_score
        allowed = score >= self.min_probability_score
        return GapAssessment(
            allowed=allowed,
            probability_score=round(score, 3),
            reason="strong trend and strong EOD close support next-day gap" if allowed else "weak gap probability from close/body/trend quality",
        )

    @staticmethod
    def _macd_supports(row: pd.Series, side: Side) -> bool:
        return float(row["macd"]) > float(row["macd_signal"]) if side == "BUY" else float(row["macd"]) < float(row["macd_signal"])
