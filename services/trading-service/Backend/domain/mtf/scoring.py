from __future__ import annotations

import pandas as pd

from Backend.domain.mtf.models import HTFTrend, LTFEntry, MTFScore, PullbackSetup, Side


class MTFScoringEngine:
    def score(self, *, htf: HTFTrend, setup: PullbackSetup, entry: LTFEntry, momentum_confirmed: bool, side: Side) -> MTFScore:
        score = MTFScore()
        score.htf_trend_alignment = 3 if htf.side == side and htf.ema_aligned else 0
        score.structure_confirmation = 2 if htf.structure_confirmed else 0
        score.pullback_quality = 2 if setup.quality >= 2.0 else 1
        score.entry_confirmation = 2 if entry.kind == "engulfing" else 1
        score.momentum_confirmation = 1 if momentum_confirmed else 0
        score.reasons = [
            htf.reason,
            setup.reason,
            entry.reason,
            "MACD confirms direction" if momentum_confirmed else "MACD does not confirm direction",
        ]
        return score

    @staticmethod
    def momentum_confirmed(candles: pd.DataFrame, index: int, side: Side) -> bool:
        row = candles.iloc[index]
        if side == "BUY":
            return float(row["macd"]) > float(row["macd_signal"])
        return float(row["macd"]) < float(row["macd_signal"])
