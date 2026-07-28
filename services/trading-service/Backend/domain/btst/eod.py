from __future__ import annotations

import logging

import pandas as pd

from Backend.domain.btst.models import EODConfirmation, Side


logger = logging.getLogger(__name__)


class EODConfirmationEngine:

    def __init__(
        self,
        *,
        close_window_minutes: int = 60,
        close_strength_threshold: float = 0.70,
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
            return None


        row = candles.iloc[index]

        session = str(row["session_day"])

        session_frame = candles[
            candles["session_day"] == session
        ]


        if session_frame.empty:
            logger.debug(
                "BTST EOD reject: empty session"
            )
            return None


        timestamp = pd.Timestamp(
            row["timestamp"]
        )

        session_end = pd.Timestamp(
            session_frame["timestamp"].max()
        )


        minutes_to_close = (
            session_end - timestamp
        ).total_seconds() / 60


        #
        # Allow last hour candles
        #
        near_close = (
            0 <= minutes_to_close <= self.close_window_minutes
        )


        if not near_close:

            logger.debug(
                "BTST EOD reject: not near close "
                "time=%s minutes_left=%.2f",
                timestamp,
                minutes_to_close,
            )

            return None



        current_session = session_frame.loc[
            session_frame.index <= index
        ]


        if current_session.empty:
            return None


        day_high = float(
            current_session["high"].max()
        )

        day_low = float(
            current_session["low"].min()
        )

        close = float(
            row["close"]
        )


        day_range = max(
            day_high - day_low,
            0.01,
        )


        if side == "BUY":

            strength = (
                close - day_low
            ) / day_range

            reason = (
                "BUY close strength near day high"
            )

        else:

            strength = (
                day_high - close
            ) / day_range

            reason = (
                "SELL close strength near day low"
            )



        logger.info(
            "BTST EOD check side=%s strength=%.2f "
            "threshold=%.2f",
            side,
            strength,
            self.close_strength_threshold,
        )


        if strength < self.close_strength_threshold:

            logger.debug(
                "BTST EOD reject: weak close strength %.2f",
                strength,
            )

            return None



        return EODConfirmation(
            side,
            True,
            min(1.0, strength),
            day_high,
            day_low,
            reason,
        )