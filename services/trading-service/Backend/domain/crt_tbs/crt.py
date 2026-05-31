from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from Backend.domain.crt_tbs.liquidity import LiquiditySweep


@dataclass(frozen=True, slots=True)
class CRTCandle:
    high: float
    low: float
    midpoint: float
    range: float
    timestamp: str
    index: int

    def to_dict(self) -> dict:
        payload = asdict(self)
        for key in ("high", "low", "midpoint", "range"):
            payload[key] = round(float(payload[key]), 4)
        return payload


class CRTDetector:
    def __init__(self, lookback: int = 12, displacement_multiplier: float = 1.35, min_body_pct: float = 0.55) -> None:
        self.lookback = int(lookback)
        self.displacement_multiplier = float(displacement_multiplier)
        self.min_body_pct = float(min_body_pct)

    def is_crt_candle(self, candles: pd.DataFrame, index: int) -> bool:
        if index < 5 or index >= len(candles):
            return False
        row = candles.iloc[index]
        ranges = candles["bar_range"].iloc[max(0, index - self.lookback) : index]
        average_range = float(ranges.mean() or 0.0)
        bar_range = float(row["bar_range"])
        body = float(row["body_size"])
        if average_range <= 0 or bar_range <= 0:
            return False
        return bar_range >= average_range * self.displacement_multiplier and body / bar_range >= self.min_body_pct

    def find_recent(self, candles: pd.DataFrame, index: int) -> CRTCandle | None:
        left = max(0, index - self.lookback)
        for candidate_index in range(index - 1, left - 1, -1):
            if self.is_crt_candle(candles, candidate_index):
                return self._build(candles, candidate_index)
        return None

    def setup_direction(self, crt: CRTCandle, row: pd.Series, sweep: LiquiditySweep) -> str | None:
        close = float(row["close"])
        inside_range = float(crt.low) < close < float(crt.high)
        if not inside_range:
            return None
        if sweep.type == "SSL" and close > float(crt.midpoint):
            return "BUY"
        if sweep.type == "BSL" and close < float(crt.midpoint):
            return "SELL"
        return None

    def setup_type(self, crt: CRTCandle, row: pd.Series, side: str) -> str:
        close = float(row["close"])
        previous_close = float(row.get("previous_close", close))
        if side.upper() == "BUY":
            return "CRT reversal" if previous_close < float(crt.midpoint) <= close else "CRT continuation"
        return "CRT reversal" if previous_close > float(crt.midpoint) >= close else "CRT continuation"

    def _build(self, candles: pd.DataFrame, index: int) -> CRTCandle:
        row = candles.iloc[index]
        high = float(row["high"])
        low = float(row["low"])
        return CRTCandle(
            high=high,
            low=low,
            midpoint=(high + low) / 2.0,
            range=high - low,
            timestamp=pd.Timestamp(row["timestamp"]).isoformat(),
            index=int(index),
        )
