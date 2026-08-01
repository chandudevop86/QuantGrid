from __future__ import annotations

import pandas as pd

from Backend.domain.breakout.models import (
    BreakoutScore,
    BreakoutSetup,
    Side,
)


class BreakoutScoringEngine:

    def score(
        self,
        row: pd.Series,
        setup: BreakoutSetup,
        *,
        trend_aligned: bool,
    ) -> BreakoutScore:

        side = setup.side
        score = BreakoutScore()

        # 1. Trend Alignment (0-3)
        score.trend_alignment = (
            3 if trend_aligned else 0
        )

        # 2. Breakout Strength (0-3)
        score.breakout_strength = (
            self._breakout_strength(setup)
        )

        # 3. Momentum (0-2)
        score.momentum_confirmation = (
            self._momentum_score(row, side)
        )

        # 4. VWAP (0-1)
        score.distance_from_vwap = (
            1 if self._vwap_edge(row, side) else 0
        )

        # 5. ATR Expansion (0-1)
        score.volatility_expansion = (
            1
            if 0.5 <= setup.candle_range_atr <= 1.5
            else 0
        )


        # ===============================
        # NEW FILTERS
        # ===============================

        # 6. Volume Confirmation (0-2)

        # Volume Confirmation
        score.volume_confirmation = 0
        volume_ratio = float(row.get("volume_ratio", 0))

        if volume_ratio >= 1.5:
            score.volume_confirmation = 2


        # ADX Trend Strength
        score.adx_strength = 0
        adx_value = float(row.get("adx", 0))

        if adx_value >= 20:
            score.adx_strength = 2


        # Candle Quality
        score.candle_quality = 0
        candle_ratio = float(row.get("candle_body_ratio", 0))

        if candle_ratio >= 0.60:
            score.candle_quality = 1
        # store extra metadata if model supports
        

        score.reasons = [

            (
                "EMA50/EMA200 trend aligned"
                if trend_aligned
                else
                "trend not aligned"
            ),

            setup.reason,

            (
                "RSI/MACD momentum confirmed"
                if score.momentum_confirmation == 2
                else
                "momentum incomplete"
            ),

            (
                "volume breakout confirmed"
                if score.volume_confirmation == 2
                else
                "weak volume"
            ),

            (
                "ADX trend strong"
                if score.adx_strength == 2
                else
                "weak trend strength"
            ),

            (
                "strong candle body"
                if score.candle_quality == 1
                else
                "weak candle"
            ),

            f"FINAL SCORE {score.total}/15"
        ]


        return score



    @staticmethod
    def _breakout_strength(
        setup: BreakoutSetup
    ) -> int:

        ratio = (
            setup.breakout_distance /
            max(
                setup.breakout_range.atr,
                0.01
            )
        )


        if ratio >= 0.35:
            return 3

        if ratio >= 0.20:
            return 2

        if ratio > 0:
            return 1

        return 0



    @staticmethod
    def _momentum_score(
        row: pd.Series,
        side: Side
    ) -> int:

        rsi = float(
            row.get("rsi",50)
        )

        macd = float(
            row.get("macd",0)
        )

        signal = float(
            row.get("macd_signal",0)
        )


        if side == "BUY":

            if rsi > 55 and macd > signal:
                return 2

        else:

            if rsi < 45 and macd < signal:
                return 2


        return 0



    @staticmethod
    def _vwap_edge(
        row: pd.Series,
        side: Side
    ) -> bool:

        close = float(
            row.get("close",0)
        )

        vwap = float(
            row.get("vwap",0)
        )


        atr = float(
            row.get(
                "atr_14",
                row.get("avg_range_5",0)
            )
            or 0
        )


        min_distance = max(
            close * 0.0003,
            atr * 0.05
        )


        if side == "BUY":
            return close > vwap + min_distance


        return close < vwap - min_distance