from __future__ import annotations

import pandas as pd

from Backend.domain.supply_demand.models import EntryConfirmation, HTFBias, LiquidityEvent, SDScore, SDZone, Side


class SDScoringEngine:
    def score(
        self,
        *,
        zone: SDZone,
        htf_bias: HTFBias,
        entry: EntryConfirmation,
        liquidity: LiquidityEvent | None,
        momentum_confirmed: bool,
        side: Side,
    ) -> SDScore:
        score = SDScore()
        score.zone_freshness = 3 if zone.touches == 0 else 2 if zone.touches == 1 else 0
        score.htf_alignment = 2 if htf_bias.aligns(side) else 0
        score.entry_confirmation = 2 if entry.kind == "engulfing" else 1
        score.liquidity_sweep = 2 if liquidity and liquidity.quality >= 2 else 1 if liquidity else 0
        score.momentum_confirmation = 1 if momentum_confirmed else 0
        score.reasons = [
            f"{zone.zone_type} zone from base + impulse, touches={zone.touches}",
            htf_bias.reason,
            entry.reason,
            liquidity.reason if liquidity else "no liquidity sweep confirmation",
            "momentum confirmed" if momentum_confirmed else "momentum not confirmed",
        ]
        return score

    @staticmethod
    def momentum_confirmed(candles: pd.DataFrame, index: int, side: Side) -> bool:
        if index < 3:
            return False
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        rsi_now = float(row["rsi"])
        rsi_prev = float(previous["rsi"])
        macd_now = float(row["macd"])
        macd_signal = float(row["macd_signal"])
        macd_prev = float(previous["macd"])
        macd_signal_prev = float(previous["macd_signal"])
        if side == "BUY":
            rsi_ok = rsi_now > rsi_prev and rsi_prev <= 45.0
            macd_ok = macd_now > macd_signal or macd_now > macd_prev > macd_signal_prev
            return rsi_ok and macd_ok
        rsi_ok = rsi_now < rsi_prev and rsi_prev >= 55.0
        macd_ok = macd_now < macd_signal or macd_now < macd_prev < macd_signal_prev
        return rsi_ok and macd_ok
