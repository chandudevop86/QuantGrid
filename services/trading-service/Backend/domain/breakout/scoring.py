from __future__ import annotations

import pandas as pd

from Backend.domain.breakout.models import BreakoutScore, BreakoutSetup, Side


class BreakoutScoringEngine:
    def score(self, row: pd.Series, setup: BreakoutSetup, *, trend_aligned: bool) -> BreakoutScore:
        side = setup.side
        score = BreakoutScore()
        score.trend_alignment = 3 if trend_aligned else 0
        score.breakout_strength = self._breakout_strength(setup)
        score.momentum_confirmation = self._momentum_score(row, side)
        score.distance_from_vwap = 1 if self._vwap_edge(row, side) else 0
        score.volatility_expansion = 1 if 0.5 <= setup.candle_range_atr <= 1.5 else 0
        score.reasons = [
            "EMA50/EMA200 trend aligned" if trend_aligned else "trend not aligned",
            setup.reason,
            "RSI/MACD momentum confirmed" if score.momentum_confirmation == 2 else "momentum incomplete",
            "clean distance from VWAP" if score.distance_from_vwap else "too close to or wrong side of VWAP",
            "ATR expansion acceptable" if score.volatility_expansion else "ATR expansion invalid",
        ]
        return score

    @staticmethod
    def _breakout_strength(setup: BreakoutSetup) -> int:
        ratio = setup.breakout_distance / max(setup.breakout_range.atr, 0.01)
        if ratio >= 0.35:
            return 3
        if ratio >= 0.20:
            return 2
        if ratio > 0:
            return 1
        return 0

    @staticmethod
    def _momentum_score(row: pd.Series, side: Side) -> int:
        if side == "BUY":
            rsi_ok = float(row["rsi"]) > 55.0
            macd_ok = float(row["macd"]) > float(row["macd_signal"])
        else:
            rsi_ok = float(row["rsi"]) < 45.0
            macd_ok = float(row["macd"]) < float(row["macd_signal"])
        return 2 if rsi_ok and macd_ok else 0

    @staticmethod
    def _vwap_edge(row: pd.Series, side: Side) -> bool:
        close = float(row["close"])
        vwap = float(row["vwap"])
        min_distance = max(close * 0.0003, float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0) * 0.05)
        if side == "BUY":
            return close > vwap + min_distance
        return close < vwap - min_distance
