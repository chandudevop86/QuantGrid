from __future__ import annotations

import pandas as pd

from Backend.domain.mtf.models import PullbackSetup, Side


class MTFSetupDetector:
    def detect(self, mtf_candles: pd.DataFrame | None, ltf_row: pd.Series, side: Side) -> PullbackSetup | None:
        frame = self._frame_until(mtf_candles, ltf_row)
        if frame.empty:
            return None
        row = frame.iloc[-1]
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.01)
        tolerance = max(atr * 0.25, float(row["close"]) * 0.0005, 0.02)
        touched_ema = float(row["low"]) <= float(row["ema_21"]) + tolerance <= float(row["high"]) if side == "BUY" else float(row["low"]) <= float(row["ema_21"]) - tolerance <= float(row["high"])
        touched_vwap = float(row["low"]) <= float(row["vwap"]) + tolerance and float(row["high"]) >= float(row["vwap"]) - tolerance

        if side == "BUY":
            pullback_valid = (touched_ema or touched_vwap) and float(row["close"]) >= min(float(row["ema_21"]), float(row["vwap"]))
        else:
            pullback_valid = (touched_ema or touched_vwap) and float(row["close"]) <= max(float(row["ema_21"]), float(row["vwap"]))
        if not pullback_valid:
            return None
        quality = (1.0 if touched_ema else 0.0) + (1.0 if touched_vwap else 0.0)
        return PullbackSetup(side, touched_ema, touched_vwap, quality, int(row.name), "5m pullback into EMA21/VWAP")

    @staticmethod
    def _frame_until(mtf_candles: pd.DataFrame | None, ltf_row: pd.Series) -> pd.DataFrame:
        if mtf_candles is None or mtf_candles.empty:
            return pd.DataFrame([ltf_row])
        timestamp = pd.Timestamp(ltf_row["timestamp"])
        return mtf_candles[mtf_candles["timestamp"] <= timestamp]
