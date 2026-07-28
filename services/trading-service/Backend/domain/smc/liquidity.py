from __future__ import annotations

import logging

import pandas as pd

from Backend.domain.smc.models import (
    LiquidityRange,
    LiquiditySweep,
    Side,
)

logger = logging.getLogger(__name__)


class LiquiditySweepDetector:
    """
    Balanced liquidity sweep detector.

    Goals
    -----
    • Detect more real institutional ranges.
    • Avoid excessive false positives.
    • Work consistently across multiple instruments.
    """

    def __init__(
        self,
        *,
        equal_level_tolerance_atr: float = 0.30,
        min_equal_touches: int = 2,
        consolidation_atr_multiplier: float = 6.0,
        consolidation_range_pct: float = 0.02,
        min_wick_extension_atr: float = 0.05,
    ) -> None:

        self.equal_level_tolerance_atr = float(equal_level_tolerance_atr)
        self.min_equal_touches = int(min_equal_touches)
        self.consolidation_atr_multiplier = float(
            consolidation_atr_multiplier
        )
        self.consolidation_range_pct = float(
            consolidation_range_pct
        )
        self.min_wick_extension_atr = float(
            min_wick_extension_atr
        )

    # -------------------------------------------------------
    # Liquidity Range
    # -------------------------------------------------------

    def detect_range(
        self,
        candles: pd.DataFrame,
        index: int,
        lookback: int,
    ) -> LiquidityRange | None:

        if index < max(5, lookback):
            return None

        start = max(0, index - lookback)

        window = candles.iloc[start:index]

        if window.empty:
            return None

        range_high = float(window["high"].max())
        range_low = float(window["low"].min())

        width = range_high - range_low

        atr = max(
            float(
                candles.iloc[index].get(
                    "atr_14",
                    candles.iloc[index].get(
                        "avg_range_5",
                        0.0,
                    ),
                )
                or 0.0
            ),
            0.01,
        )

        avg_bar = max(
            float(window["bar_range"].mean() or 0.0),
            0.01,
        )

        tolerance = max(
            atr * self.equal_level_tolerance_atr,
            width * 0.02,
            range_high * 0.0005,
            0.01,
        )

        equal_highs = int(
            (
                window["high"]
                .sub(range_high)
                .abs()
                <= tolerance
            ).sum()
        )

        equal_lows = int(
            (
                window["low"]
                .sub(range_low)
                .abs()
                <= tolerance
            ).sum()
        )

        consolidation_limit = max(
            avg_bar * 6.0,
            atr * self.consolidation_atr_multiplier,
            range_high * self.consolidation_range_pct,
        )

        if width > consolidation_limit:
            logger.debug(
                "Liquidity rejected: width %.2f > %.2f",
                width,
                consolidation_limit,
            )
            return None

        if (
            equal_highs < self.min_equal_touches
            and equal_lows < self.min_equal_touches
        ):
            logger.debug(
                "Liquidity rejected: highs=%d lows=%d",
                equal_highs,
                equal_lows,
            )
            return None

        logger.debug(
            "Liquidity range detected "
            "(%.2f - %.2f)",
            range_low,
            range_high,
        )

        return LiquidityRange(
            high=range_high,
            low=range_low,
            start_index=start,
            end_index=index - 1,
            equal_highs=equal_highs,
            equal_lows=equal_lows,
            atr=atr,
        )

    # -------------------------------------------------------
    # Sweep Detection
    # -------------------------------------------------------

    def detect_sweep(
        self,
        candles: pd.DataFrame,
        index: int,
        liquidity_range: LiquidityRange,
        side: Side,
    ) -> LiquiditySweep | None:

        row = candles.iloc[index]

        atr = max(
            float(
                row.get(
                    "atr_14",
                    liquidity_range.atr,
                )
                or liquidity_range.atr
            ),
            0.01,
        )

        close = float(row["close"])

        high = float(row["high"])
        low = float(row["low"])

        midpoint = liquidity_range.midpoint

        # ---------------- SELL ----------------

        if side == "SELL":

            wick_break = high > liquidity_range.high

            extension = high - liquidity_range.high

            extension_ok = (
                extension >= atr * self.min_wick_extension_atr
            )

            close_returned = (
                close <= liquidity_range.high
            )

            if not (
                wick_break
                and extension_ok
                and close_returned
            ):
                return None

            quality = 1.0

            quality += min(
                extension / atr,
                1.0,
            )

            if close < midpoint:
                quality += 0.75

            if extension > atr:
                quality += 0.25

            quality = min(
                3.0,
                quality,
            )

            return LiquiditySweep(
                side="SELL",
                swept_level=liquidity_range.high,
                sweep_index=index,
                sweep_price=high,
                close_price=close,
                quality=quality,
                direction="SELL",
            )

        # ---------------- BUY ----------------

        wick_break = low < liquidity_range.low

        extension = liquidity_range.low - low

        extension_ok = (
            extension >= atr * self.min_wick_extension_atr
        )

        close_returned = (
            close >= liquidity_range.low
        )

        if not (
            wick_break
            and extension_ok
            and close_returned
        ):
            return None

        quality = 1.0

        quality += min(
            extension / atr,
            1.0,
        )

        if close > midpoint:
            quality += 0.75

        if extension > atr:
            quality += 0.25

        quality = min(
            3.0,
            quality,
        )

        return LiquiditySweep(
            side="BUY",
            swept_level=liquidity_range.low,
            sweep_index=index,
            sweep_price=low,
            close_price=close,
            quality=quality,
            direction="BUY",
        )