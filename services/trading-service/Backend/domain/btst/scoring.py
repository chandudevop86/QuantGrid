from __future__ import annotations

import pandas as pd

from Backend.domain.btst.models import BTSTScore, EODConfirmation, Side, SwingStructure


class BTSTScoringEngine:
    def score(self, *, row: pd.Series, side: Side, structure: SwingStructure, eod: EODConfirmation) -> BTSTScore:
        score = BTSTScore()
        score.trend_alignment = 3 if structure.side == side and structure.trend in {"bullish", "bearish"} else 0
        score.structure_breakout = 3 if structure.structure_confirmed and structure.breakout_confirmed else 0
        score.eod_strength = 2 if eod.close_strength >= 0.85 else 1
        score.momentum_confirmation = 1 if self.momentum_confirmed(row, side) else 0
        score.vwap_alignment = 1 if self.vwap_aligned(row, side) else 0
        score.reasons = [
            structure.reason,
            eod.reason,
            "momentum supports direction" if score.momentum_confirmation else "momentum does not support direction",
            "VWAP aligned" if score.vwap_alignment else "VWAP not aligned",
        ]
        return score

    @staticmethod
    def momentum_confirmed(row: pd.Series, side: Side) -> bool:
        if side == "BUY":
            return float(row["rsi"]) > 55.0 and float(row["macd"]) > float(row["macd_signal"])
        return float(row["rsi"]) < 45.0 and float(row["macd"]) < float(row["macd_signal"])

    @staticmethod
    def vwap_aligned(row: pd.Series, side: Side) -> bool:
        return float(row["close"]) > float(row["vwap"]) if side == "BUY" else float(row["close"]) < float(row["vwap"])
