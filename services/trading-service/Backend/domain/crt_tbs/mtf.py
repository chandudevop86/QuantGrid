from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService


@dataclass(frozen=True, slots=True)
class MTFBias:
    h4_bias: str
    h1_bias: str
    aligned: bool

    @property
    def bias(self) -> str:
        if self.h4_bias == self.h1_bias:
            return self.h1_bias
        if self.h1_bias != "NEUTRAL":
            return self.h1_bias
        return self.h4_bias

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["bias"] = self.bias
        return payload


class MultiTimeframeAnalyzer:
    def __init__(self, indicators: IndicatorService | None = None) -> None:
        self.indicators = indicators or IndicatorService()

    def analyze(self, context_params: dict[str, Any], side: str, fallback: pd.DataFrame) -> MTFBias:
        h4 = self._prepare(context_params.get("h4_candles") or context_params.get("daily_candles"))
        h1 = self._prepare(context_params.get("h1_candles") or context_params.get("htf_candles"))
        fallback_bias = self._bias(fallback)
        h4_bias = self._bias(h4) if h4 is not None else fallback_bias
        h1_bias = self._bias(h1) if h1 is not None else fallback_bias
        desired = "BULLISH" if side.upper() == "BUY" else "BEARISH"
        return MTFBias(h4_bias=h4_bias, h1_bias=h1_bias, aligned=desired in {h4_bias, h1_bias} and h1_bias != self._opposite(desired))

    def _prepare(self, data: Any) -> pd.DataFrame | None:
        if data is None:
            return None
        frame = self.indicators.prepare(data)
        return frame if not frame.empty else None

    @staticmethod
    def _bias(frame: pd.DataFrame | None) -> str:
        if frame is None or frame.empty:
            return "NEUTRAL"
        row = frame.iloc[-1]
        close = float(row["close"])
        ema21 = float(row["ema_21"])
        ema50 = float(row["ema_50"])
        ema200 = float(row["ema_200"])
        if close > ema21 > ema50:
            return "BULLISH"
        if close < ema21 < ema50:
            return "BEARISH"
        if close > ema200:
            return "BULLISH"
        if close < ema200:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _opposite(bias: str) -> str:
        return "BEARISH" if bias == "BULLISH" else "BULLISH"
