from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd


SweepType = Literal["BSL", "SSL"]


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    type: SweepType
    level: float
    swept: bool
    timestamp: str
    source: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["level"] = round(float(self.level), 4)
        return payload


class LiquiditySweepDetector:
    def __init__(self, lookback: int = 20, equal_tolerance_pct: float = 0.0006) -> None:
        self.lookback = int(lookback)
        self.equal_tolerance_pct = float(equal_tolerance_pct)

    def detect(self, candles: pd.DataFrame, index: int) -> list[LiquiditySweep]:
        if index < 3 or index >= len(candles):
            return []

        row = candles.iloc[index]
        window = candles.iloc[max(0, index - self.lookback) : index]
        if window.empty:
            return []

        timestamp = pd.Timestamp(row["timestamp"]).isoformat()
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        previous_high = float(window["high"].max())
        previous_low = float(window["low"].min())
        sweeps: list[LiquiditySweep] = []

        if high > previous_high and close < previous_high:
            sweeps.append(LiquiditySweep("BSL", previous_high, True, timestamp, self._high_source(window, previous_high)))
        if low < previous_low and close > previous_low:
            sweeps.append(LiquiditySweep("SSL", previous_low, True, timestamp, self._low_source(window, previous_low)))

        return sweeps

    def detect_primary(self, candles: pd.DataFrame, index: int, side: str | None = None) -> LiquiditySweep | None:
        sweeps = self.detect(candles, index)
        if not sweeps:
            return None
        if side and side.upper() == "BUY":
            return next((sweep for sweep in sweeps if sweep.type == "SSL"), None)
        if side and side.upper() == "SELL":
            return next((sweep for sweep in sweeps if sweep.type == "BSL"), None)
        return sweeps[0]

    def _high_source(self, window: pd.DataFrame, level: float) -> str:
        equal_count = self._near_count(window["high"], level)
        return "equal_highs" if equal_count >= 2 else "previous_swing_high"

    def _low_source(self, window: pd.DataFrame, level: float) -> str:
        equal_count = self._near_count(window["low"], level)
        return "equal_lows" if equal_count >= 2 else "previous_swing_low"

    def _near_count(self, series: pd.Series, level: float) -> int:
        tolerance = max(abs(float(level)) * self.equal_tolerance_pct, 0.01)
        return int(((series.astype(float) - float(level)).abs() <= tolerance).sum())
