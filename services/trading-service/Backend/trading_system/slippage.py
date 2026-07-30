from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

SlippageMode = Literal["fixed", "volatility", "combined"]


@dataclass(slots=True)
class SlippageConfig:
    # fixed = only fixed bps
    # volatility = only ATR based
    # combined = fixed + ATR
    mode: SlippageMode = "combined"

    # 0.5 basis points (~0.12 points at NIFTY 24,000)
    fixed_bps: float = 0.5

    # 0.5% of ATR
    atr_factor: float = 0.005

    atr_period: int = 14

    # Absolute cap in points
    max_slippage_points: float = 2.0


class SlippageModel:
    def __init__(self, config: SlippageConfig | None = None) -> None:
        self.config = config or SlippageConfig()

    def amount(
        self,
        price: float,
        candles: pd.DataFrame | None = None,
        index: int | None = None,
    ) -> float:

        price = float(price)

        # Fixed component
        fixed = price * self.config.fixed_bps / 10000.0

        # ATR component
        volatility = 0.0

        if (
            candles is not None
            and index is not None
            and len(candles) > 0
        ):
            atr = self._atr(
                candles,
                index,
                self.config.atr_period,
            )

            volatility = atr * self.config.atr_factor

        if self.config.mode == "fixed":
            slip = fixed

        elif self.config.mode == "volatility":
            slip = volatility

        else:
            slip = fixed + volatility

        # Hard cap in points
        slip = min(
            slip,
            self.config.max_slippage_points,
        )

        return max(0.0, slip)

    def apply(
        self,
        price: float,
        side: str,
        event: Literal["entry", "exit"],
        candles: pd.DataFrame | None = None,
        index: int | None = None,
    ) -> float:

        slip = self.amount(
            price,
            candles,
            index,
        )

        side = side.upper()

        if event == "entry":

            if side == "BUY":
                return float(price) + slip

            return float(price) - slip

        # Exit

        if side == "BUY":
            return float(price) - slip

        return float(price) + slip

    @staticmethod
    def _atr(
        candles: pd.DataFrame,
        index: int,
        period: int,
    ) -> float:

        start = max(
            0,
            index - period + 1,
        )

        window = candles.iloc[start:index + 1]

        if window.empty:
            return 0.0

        prev_close = window["close"].shift(1)

        tr = pd.concat(
            [
                window["high"] - window["low"],
                (window["high"] - prev_close).abs(),
                (window["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr = tr.mean(skipna=True)

        if pd.isna(atr):
            return 0.0

        return float(atr)