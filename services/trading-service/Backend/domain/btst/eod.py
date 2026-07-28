from __future__ import annotations

import logging

import pandas as pd

from Backend.domain.btst.models import EODConfirmation, Side

logger = logging.getLogger(__name__)


class EODConfirmationEngine:
    def __init__(
        self,
        *,
        close_window_minutes: int = 30,
        close_strength_threshold: float = 0.75,
    ) -> None:
        self.close_window_minutes = int(close_window_minutes)
        self.close_strength_threshold = float(close_strength_threshold)

    def confirm(
        self,
        candles: pd.DataFrame,
        index: int,
        side: Side,
    ) -> EODConfirmation | None:

        if candles.empty:
            logger.info("BTST EOD Reject: empty dataframe")
            return None

        row = candles.iloc[index]

        session = str(row["session_day"])

        session_frame = candles[candles["session_day"] == session]

        if session_frame.empty:
            logger.info(
                "BTST EOD Reject: session=%s not found",
                session,
            )
            return None

        timestamp = pd.Timestamp(row["timestamp"])
        session_end = pd.Timestamp(session_frame["timestamp"].max())

        minutes_to_close = (
            session_end - timestamp
        ).total_seconds() / 60.0

        near_close = (
            0.0 <= minutes_to_close <= self.close_window_minutes
        )

        if not near_close:
            logger.info(
                "BTST EOD Reject: %s "
                "minutes_to_close=%.1f allowed<=%d",
                timestamp,
                minutes_to_close,
                self.close_window_minutes,
            )
            return None

        history = session_frame[
            session_frame["timestamp"] <= timestamp
        ]

        if history.empty:
            logger.info(
                "BTST EOD Reject: no intraday history"
            )
            return None

        day_high = float(history["high"].max())
        day_low = float(history["low"].min())

        day_range = max(day_high - day_low, 0.01)

        close = float(row["close"])

        if side == "BUY":
            strength = (close - day_low) / day_range
        else:
            strength = (day_high - close) / day_range

        if strength < self.close_strength_threshold:
            logger.info(
                "BTST EOD Reject: %s "
                "strength=%.3f required=%.3f "
                "side=%s close=%.2f high=%.2f low=%.2f",
                timestamp,
                strength,
                self.close_strength_threshold,
                side,
                close,
                day_high,
                day_low,
            )
            return None

        reason = (
            "close near day high into EOD"
            if side == "BUY"
            else "close near day low into EOD"
        )

        logger.info(
            "BTST EOD PASS: %s "
            "side=%s strength=%.3f "
            "minutes_to_close=%.1f",
            timestamp,
            side,
            strength,
            minutes_to_close,
        )

        return EODConfirmation(
            side=side,
            near_close=True,
            close_strength=min(1.0, strength),
            day_high=day_high,
            day_low=day_low,
            reason=reason,
        )