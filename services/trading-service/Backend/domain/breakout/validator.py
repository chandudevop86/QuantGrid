from __future__ import annotations

import pandas as pd

from Backend.domain.breakout.models import BreakoutSetup, Side


class BreakoutSignalValidator:
    def __init__(self, *, min_score: int = 7, avoid_open_minutes: int = 5) -> None:
        self.min_score = int(min_score)
        self.avoid_open_minutes = int(avoid_open_minutes)

    def session_open_allowed(self, candles: pd.DataFrame, index: int) -> bool:
        row = candles.iloc[index]
        session = str(row["session_day"])
        session_frame = candles[candles["session_day"] == session]
        if session_frame.empty:
            return True
        session_open = pd.Timestamp(session_frame["timestamp"].min())
        timestamp = pd.Timestamp(row["timestamp"])
        return (timestamp - session_open).total_seconds() / 60.0 >= self.avoid_open_minutes

    def valid_signal(self, *, score: int, setup: BreakoutSetup | None, trend_aligned: bool) -> tuple[bool, str]:
        if setup is None:
            return False, "no close-confirmed breakout"
        if not trend_aligned:
            return False, "trend filter rejected side"
        if score < self.min_score:
           return False, f"score {score}/{self.min_score} below threshold"
        return True, "accepted"
