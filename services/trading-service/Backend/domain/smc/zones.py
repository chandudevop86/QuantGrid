from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from Backend.domain.smc.models import (
    FVGZone,
    Side,
    SupplyDemandZone,
)

logger = logging.getLogger(__name__)


class ZoneConfluenceEngine:
    """
    Balanced Supply/Demand Zone detector.

    • FVG-backed zones preferred
    • Falls back to swing highs/lows
    • Adaptive ATR sizing
    • Moderate filtering
    """

    def __init__(
        self,
        *,
        lookback: int = 48,
        max_touches: int = 2,
        zone_width_atr: float = 0.80,
        minimum_overlap: float = 0.20,
    ) -> None:

        self.lookback = int(lookback)
        self.max_touches = int(max_touches)
        self.zone_width_atr = float(zone_width_atr)
        self.minimum_overlap = float(minimum_overlap)

    # ---------------------------------------------------------

    def _zone_from_fvg(
        self,
        candles: pd.DataFrame,
        index: int,
        side: Side,
        fvg: FVGZone,
    ) -> SupplyDemandZone:

        zone_type: Literal["supply", "demand"]

        zone_type = "demand" if side == "BUY" else "supply"

        zone = SupplyDemandZone(
            zone_type=zone_type,
            low=fvg.low,
            high=fvg.high,
            created_index=fvg.created_index,
        )

        zone.touches = self.count_touches(
            candles,
            zone,
            fvg.created_index + 1,
            index - 1,
        )

        return zone

    # ---------------------------------------------------------

    def find_zone(
        self,
        candles: pd.DataFrame,
        index: int,
        side: Side,
        *,
        fvg: FVGZone | None = None,
        after_index: int | None = None,
    ) -> SupplyDemandZone | None:

        start = max(
            0,
            after_index if after_index is not None else index - self.lookback,
        )

        window = candles.iloc[start:index]

        if len(window) < 5:
            return None

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

        zone_width = atr * self.zone_width_atr

        # ------------------------
        # Prefer FVG zone
        # ------------------------

        if fvg is not None:

            zone = self._zone_from_fvg(
                candles,
                index,
                side,
                fvg,
            )

            if zone.touches <= self.max_touches:
                logger.debug(
                    "Using FVG backed zone"
                )
                return zone

        # ------------------------
        # Demand
        # ------------------------

        if side == "BUY":

            anchor_index = int(window["low"].idxmin())

            anchor = candles.loc[anchor_index]

            low = float(anchor["low"])

            high = low + zone_width

            zone = SupplyDemandZone(
                zone_type="demand",
                low=low,
                high=high,
                created_index=anchor_index,
            )

        # ------------------------
        # Supply
        # ------------------------

        else:

            anchor_index = int(window["high"].idxmax())

            anchor = candles.loc[anchor_index]

            high = float(anchor["high"])

            low = high - zone_width

            zone = SupplyDemandZone(
                zone_type="supply",
                low=low,
                high=high,
                created_index=anchor_index,
            )

        zone.touches = self.count_touches(
            candles,
            zone,
            zone.created_index + 1,
            index - 1,
        )

        if zone.touches > self.max_touches:
            return None

        return zone

    # ---------------------------------------------------------

    def has_confluence(
        self,
        zone: SupplyDemandZone,
        fvg: FVGZone,
    ) -> bool:

        overlap_low = max(
            zone.low,
            fvg.low,
        )

        overlap_high = min(
            zone.high,
            fvg.high,
        )

        overlap = overlap_high - overlap_low

        if overlap <= 0:
            return False

        smaller = min(
            zone.high - zone.low,
            fvg.high - fvg.low,
        )

        if smaller <= 0:
            return False

        return (overlap / smaller) >= self.minimum_overlap

    # ---------------------------------------------------------

    @staticmethod
    def count_touches(
        candles: pd.DataFrame,
        zone: SupplyDemandZone,
        start: int,
        end: int,
    ) -> int:

        if end < start:
            return 0

        window = candles.iloc[start : end + 1]

        return int(
            (
                (window["low"] <= zone.high)
                &
                (window["high"] >= zone.low)
            ).sum()
        )