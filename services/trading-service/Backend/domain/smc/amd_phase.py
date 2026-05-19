from __future__ import annotations

import pandas as pd

from Backend.domain.smc.liquidity import LiquiditySweepDetector
from Backend.domain.smc.models import AMDContext, Side


class AMDPhaseDetector:
    def __init__(self, sweep_detector: LiquiditySweepDetector | None = None) -> None:
        self.sweep_detector = sweep_detector or LiquiditySweepDetector()

    def detect(self, candles: pd.DataFrame, index: int, *, side: Side, range_lookback: int, distribution_lookback: int) -> AMDContext | None:
        search_start = max(range_lookback, index - distribution_lookback)
        for sweep_index in range(index - 1, search_start - 1, -1):
            liquidity_range = self.sweep_detector.detect_range(candles, sweep_index, range_lookback)
            if liquidity_range is None:
                continue
            sweep = self.sweep_detector.detect_sweep(candles, sweep_index, liquidity_range, side)
            if sweep is None:
                continue
            strength = self._distribution_strength(candles, sweep_index, index, side)
            if strength < 1.0:
                continue
            return AMDContext(
                phase="distribution",
                liquidity_range=liquidity_range,
                sweep=sweep,
                distribution_index=index,
                strength=min(3.0, strength),
            )
        return None

    @staticmethod
    def _distribution_strength(candles: pd.DataFrame, sweep_index: int, index: int, side: Side) -> float:
        if index <= sweep_index:
            return 0.0
        window = candles.iloc[sweep_index + 1 : index + 1]
        if window.empty:
            return 0.0
        atr = max(float(candles.iloc[index].get("atr_14", candles.iloc[index].get("avg_range_5", 0.0)) or 0.0), 0.01)
        move = float(window["close"].iloc[-1]) - float(candles.iloc[sweep_index]["close"])
        impulse = -move if side == "SELL" else move
        impulse_score = max(0.0, impulse / atr)
        body_ratio = float((window["body_size"] / window["bar_range"].replace(0.0, pd.NA)).mean(skipna=True) or 0.0)
        return impulse_score + body_ratio
