from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from Backend.domain.crt_tbs.liquidity import LiquiditySweep


@dataclass(frozen=True, slots=True)
class TBSSetup:
    trap_type: str
    entry_zone: tuple[float, float]
    stop_loss: float
    confidence: float

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["entry_zone"] = [round(float(item), 4) for item in self.entry_zone]
        payload["stop_loss"] = round(float(self.stop_loss), 4)
        payload["confidence"] = round(float(self.confidence), 2)
        return payload


class TBSDetector:
    def __init__(self, range_lookback: int = 20, stop_buffer_pct: float = 0.0008) -> None:
        self.range_lookback = int(range_lookback)
        self.stop_buffer_pct = float(stop_buffer_pct)

    def detect(self, candles: pd.DataFrame, index: int, sweep: LiquiditySweep) -> TBSSetup | None:
        if index < 3:
            return None
        row = candles.iloc[index]
        window = candles.iloc[max(0, index - self.range_lookback) : index]
        if window.empty:
            return None

        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        resistance = float(window["high"].max())
        support = float(window["low"].min())
        average_range = max(float(window["bar_range"].mean() or 0.0), 0.01)
        buffer = max(close * self.stop_buffer_pct, average_range * 0.15, 0.01)

        if sweep.type == "BSL" and high > resistance and close < resistance:
            return TBSSetup(
                trap_type="bull_trap",
                entry_zone=(close, resistance),
                stop_loss=high + buffer,
                confidence=self._confidence(row, average_range),
            )
        if sweep.type == "SSL" and low < support and close > support:
            return TBSSetup(
                trap_type="bear_trap",
                entry_zone=(support, close),
                stop_loss=low - buffer,
                confidence=self._confidence(row, average_range),
            )
        return None

    @staticmethod
    def _confidence(row: pd.Series, average_range: float) -> float:
        bar_range = max(float(row["bar_range"]), 0.01)
        displacement = min(1.0, bar_range / max(float(average_range), 0.01))
        wick_ratio = 1.0 - min(1.0, float(row["body_size"]) / bar_range)
        return min(1.0, 0.45 + displacement * 0.25 + wick_ratio * 0.30)
