from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


SlippageMode = Literal["fixed", "volatility", "combined"]


@dataclass(slots=True)
class SlippageConfig:
    mode: SlippageMode = "combined"
    fixed_bps: float = 5.0
    atr_factor: float = 0.05
    atr_period: int = 14
    max_slippage_bps: float = 50.0


class SlippageModel:
    def __init__(self, config: SlippageConfig | None = None) -> None:
        self.config = config or SlippageConfig()

    def amount(self, price: float, candles: pd.DataFrame | None = None, index: int | None = None) -> float:
        price = float(price)
        fixed = price * float(self.config.fixed_bps) / 10_000.0
        volatility = 0.0
        if candles is not None and index is not None and len(candles) > 0:
            volatility = self._atr(candles, index, int(self.config.atr_period)) * float(self.config.atr_factor)

        if self.config.mode == "fixed":
            raw = fixed
        elif self.config.mode == "volatility":
            raw = volatility
        else:
            raw = fixed + volatility

        cap = price * float(self.config.max_slippage_bps) / 10_000.0
        return max(0.0, min(raw, cap))

    def apply(self, price: float, side: str, event: Literal["entry", "exit"], candles: pd.DataFrame | None = None, index: int | None = None) -> float:
        slip = self.amount(price, candles, index)
        side = side.upper()
        if event == "entry":
            return float(price) + slip if side == "BUY" else float(price) - slip
        return float(price) - slip if side == "BUY" else float(price) + slip

    @staticmethod
    def _atr(candles: pd.DataFrame, index: int, period: int) -> float:
        start = max(0, int(index) - max(1, period) + 1)
        window = candles.iloc[start : int(index) + 1]
        if window.empty:
            return 0.0

        previous_close = window["close"].shift(1)
        true_range = pd.concat(
            [
                window["high"] - window["low"],
                (window["high"] - previous_close).abs(),
                (window["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return float(true_range.mean(skipna=True) or 0.0)
