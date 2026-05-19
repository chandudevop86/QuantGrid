from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.supply_demand.models import HTFBias, Side


class HTFAnalyzer:
    def __init__(self, indicator_service: IndicatorService | None = None) -> None:
        self.indicators = indicator_service or IndicatorService()

    def prepare(self, htf_data: Any | None) -> pd.DataFrame | None:
        if htf_data is None:
            return None
        prepared = self.indicators.prepare(htf_data)
        return prepared if not prepared.empty else None

    def bias_at(self, htf_candles: pd.DataFrame | None, ltf_row: pd.Series) -> HTFBias:
        row = self._matching_row(htf_candles, ltf_row)
        ema9, ema21, ema50, ema200 = float(row["ema_9"]), float(row["ema_21"]), float(row["ema_50"]), float(row["ema_200"])
        close = float(row["close"])
        vwap = float(row["vwap"])
        if close >= vwap and ema9 >= ema21 >= ema50:
            strength = 2.0 if ema50 >= ema200 else 1.0
            return HTFBias("bullish", strength, "HTF bullish EMA/VWAP alignment")
        if close <= vwap and ema9 <= ema21 <= ema50:
            strength = 2.0 if ema50 <= ema200 else 1.0
            return HTFBias("bearish", strength, "HTF bearish EMA/VWAP alignment")
        return HTFBias("neutral", 0.0, "HTF trend is mixed")

    def aligns(self, htf_candles: pd.DataFrame | None, ltf_row: pd.Series, side: Side) -> HTFBias:
        return self.bias_at(htf_candles, ltf_row)

    @staticmethod
    def _matching_row(htf_candles: pd.DataFrame | None, ltf_row: pd.Series) -> pd.Series:
        if htf_candles is None or htf_candles.empty:
            return ltf_row
        timestamp = pd.Timestamp(ltf_row["timestamp"])
        matches = htf_candles[htf_candles["timestamp"] <= timestamp]
        return matches.iloc[-1] if not matches.empty else htf_candles.iloc[0]
