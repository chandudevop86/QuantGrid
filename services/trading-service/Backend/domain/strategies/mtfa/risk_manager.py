from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from Backend.domain.strategies.mtfa.zone_detector import MTFAZone


@dataclass(frozen=True, slots=True)
class MTFARiskPlan:
    entry: float
    stop_loss: float
    target: float
    rr: float
    capital: float
    risk_amount: float
    stop_distance: float
    position_size: int

    def to_dict(self) -> dict:
        payload = asdict(self)
        for key in ("entry", "stop_loss", "target", "rr", "capital", "risk_amount", "stop_distance"):
            payload[key] = round(float(payload[key]), 4)
        return payload


class MTFARiskManager:
    def build(self, candles: pd.DataFrame, index: int, side: str, target_zone: MTFAZone, capital: float, risk_pct: float, min_rr: float = 2.0) -> MTFARiskPlan:
        row = candles.iloc[index]
        entry = float(row["close"])
        swing_window = candles.iloc[max(0, index - 8) : index + 1]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), entry * 0.001, 0.01)
        if side.upper() == "BUY":
            stop = float(swing_window["low"].min()) - atr * 0.2
            structure_target = max(float(target_zone.high), float(swing_window["high"].max()))
            target = max(structure_target, entry + abs(entry - stop) * min_rr)
        else:
            stop = float(swing_window["high"].max()) + atr * 0.2
            structure_target = min(float(target_zone.low), float(swing_window["low"].min()))
            target = min(structure_target, entry - abs(entry - stop) * min_rr)
        stop_distance = abs(entry - stop)
        rr = abs(target - entry) / stop_distance if stop_distance > 0 else 0.0
        risk_fraction = float(risk_pct) / 100.0 if float(risk_pct) >= 1 else float(risk_pct)
        risk_amount = max(0.0, float(capital) * risk_fraction)
        size = int(risk_amount // stop_distance) if stop_distance > 0 else 0
        return MTFARiskPlan(entry, stop, target, rr, float(capital), risk_amount, stop_distance, max(0, size))
