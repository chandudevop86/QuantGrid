from __future__ import annotations

import logging

import pandas as pd

from Backend.domain.smc.liquidity import LiquiditySweepDetector
from Backend.domain.smc.models import AMDContext, Side

logger = logging.getLogger(__name__)


class AMDPhaseDetector:
    def __init__(
        self,
        sweep_detector: LiquiditySweepDetector | None = None,
    ) -> None:
        self.sweep_detector = sweep_detector or LiquiditySweepDetector()

    def detect(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        range_lookback: int,
        distribution_lookback: int,
    ) -> AMDContext | None:

        if index < range_lookback:
            return None

        search_start = max(
            range_lookback,
            index - distribution_lookback,
        )

        for sweep_index in range(
            index - 1,
            search_start - 1,
            -1,
        ):

            liquidity_range = self.sweep_detector.detect_range(
                candles,
                sweep_index,
                range_lookback,
            )

            if liquidity_range is None:
                logger.debug(
                    "AMD[%d] No liquidity range",
                    sweep_index,
                )
                continue

            sweep = self.sweep_detector.detect_sweep(
                candles,
                sweep_index,
                liquidity_range,
                side,
            )

            if sweep is None:
                logger.debug(
                    "AMD[%d] No liquidity sweep",
                    sweep_index,
                )
                continue

            strength = self._distribution_strength(
                candles,
                sweep_index,
                index,
                side,
            )

            logger.debug(
                "AMD[%d] Distribution strength = %.2f",
                sweep_index,
                strength,
            )

            if strength < 1.0:
                logger.debug(
                    "AMD[%d] Rejected (strength < 1.0)",
                    sweep_index,
                )
                continue

            logger.debug(
                "AMD detected | index=%d sweep=%d strength=%.2f",
                index,
                sweep_index,
                strength,
            )

            return AMDContext(
                phase="distribution",
                liquidity_range=liquidity_range,
                sweep=sweep,
                distribution_index=index,
                strength=min(3.0, strength),
            )

        logger.debug(
            "AMD not detected at index=%d",
            index,
        )

        return None

    @staticmethod
    def _distribution_strength(
        candles: pd.DataFrame,
        sweep_index: int,
        index: int,
        side: Side,
    ) -> float:

        if index <= sweep_index:
            return 0.0

        window = candles.iloc[
            sweep_index + 1 : index + 1
        ]

        if window.empty:
            return 0.0

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

        move = (
            float(window["close"].iloc[-1])
            - float(candles.iloc[sweep_index]["close"])
        )

        impulse = move if side == "BUY" else -move

        impulse_score = max(
            0.0,
            impulse / atr,
        )

        body_ratio = (
            window["body_size"]
            / window["bar_range"].replace(0.0, pd.NA)
        ).mean(skipna=True)

        body_ratio = (
            float(body_ratio)
            if pd.notna(body_ratio)
            else 0.0
        )

        strength = impulse_score + body_ratio

        return max(
            0.0,
            strength,
        )