from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.providers.dhan_provider import DhanProvider
from app.repository.candle_repository import candle_repository


class BackfillService:

    def __init__(self):
        self.provider = DhanProvider()

    def backfill(
        self,
        db: Session,
        symbol: str,
        security_id: str,
        exchange_segment: str,
        interval: str = "1",
        days: int = 365,
    ):

        end = date.today()

        start = end - timedelta(days=days)

        current = start

        total_saved = 0

        while current <= end:

            batch_end = min(
                current + timedelta(days=30),
                end,
            )

            candles = self.provider.get_intraday_history(
                security_id=security_id,
                exchange_segment=exchange_segment,
                interval=interval,
                from_date=current,
                to_date=batch_end,
            )

            if not candles.empty:

                total_saved += candle_repository.save_dataframe(
                    db,
                    candles,
                    symbol,
                    interval,
                )

            current = batch_end + timedelta(days=1)

        return total_saved