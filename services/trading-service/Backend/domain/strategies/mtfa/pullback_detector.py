from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from Backend.domain.strategies.mtfa.zone_detector import MTFAZone


@dataclass(frozen=True, slots=True)
class PullbackResult:
    pullback_valid: bool
    exhaustion_score: int
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class PullbackDetector:
    def detect(self, candles: pd.DataFrame, zone: MTFAZone, side: str) -> PullbackResult:
        if candles is None or candles.empty:
            return PullbackResult(False, 0, "missing 1H candles")
        recent = candles.tail(5)
        touched = any(zone.contains(float(row["low"] if side.upper() == "BUY" else row["high"]), buffer=float(row.get("atr_14", 0.0) or 0.0)) for _, row in recent.iterrows())
        score = self._exhaustion_score(recent, side)
        return PullbackResult(touched and score > 0, score, "zone pullback confirmed" if touched and score > 0 else "no valid zone pullback")

    @staticmethod
    def _exhaustion_score(candles: pd.DataFrame, side: str) -> int:
        score = 0
        for _, row in candles.iterrows():
            bar_range = max(float(row["bar_range"]), 0.01)
            body = float(row["body_size"])
            upper_wick = float(row["high"]) - max(float(row["open"]), float(row["close"]))
            lower_wick = min(float(row["open"]), float(row["close"])) - float(row["low"])
            small_body = body / bar_range <= 0.35
            if small_body:
                score += 1
            if side.upper() == "BUY" and lower_wick / bar_range >= 0.35:
                score += 1
            if side.upper() == "SELL" and upper_wick / bar_range >= 0.35:
                score += 1
        return min(score, 5)
