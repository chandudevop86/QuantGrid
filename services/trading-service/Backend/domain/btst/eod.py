from __future__ import annotations

import pandas as pd

from Backend.domain.btst.models import EODConfirmation, Side


class EODConfirmationEngine:
    def __init__(self, *, close_window_minutes: int = 30, close_strength_threshold: float = 0.75) -> None:
        self.close_window_minutes = int(close_window_minutes)
        self.close_strength_threshold = float(close_strength_threshold)

    def confirm(self, candles: pd.DataFrame, index: int, side: Side) -> EODConfirmation | None:
        row = candles.iloc[index]
        session = str(row["session_day"])
        session_frame = candles[candles["session_day"] == session]
        if session_frame.empty:
            return None
        session_end = pd.Timestamp(session_frame["timestamp"].max())
        timestamp = pd.Timestamp(row["timestamp"])
        minutes_to_close = (session_end - timestamp).total_seconds() / 60.0
        near_close = 0.0 <= minutes_to_close <= self.close_window_minutes
        if not near_close:
            return None

        day_high = float(session_frame.loc[:index, "high"].max())
        day_low = float(session_frame.loc[:index, "low"].min())
        day_range = max(day_high - day_low, 0.01)
        close = float(row["close"])
        strength = (close - day_low) / day_range if side == "BUY" else (day_high - close) / day_range
        if strength < self.close_strength_threshold:
            return None
        reason = "close near day high into EOD" if side == "BUY" else "close near day low into EOD"
        return EODConfirmation(side, near_close, min(1.0, strength), day_high, day_low, reason)
