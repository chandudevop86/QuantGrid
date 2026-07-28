from __future__ import annotations

from sqlalchemy.orm import Session

from app.providers.dhan_provider import DhanProvider
from app.repository.candle_repository import candle_repository


class MarketDataDownloader:


    def __init__(self):

        self.provider = DhanProvider()



    def download_symbol(
        self,
        db: Session,
        symbol: str,
        security_id: str,
        exchange_segment: str,
        interval: str = "1"
    ):


        if not self.provider.connected():

            raise Exception(
                "Dhan provider not connected"
            )


        candles = self.provider.get_intraday_candles(

            security_id=security_id,

            exchange_segment=exchange_segment,

            interval=interval

        )


        if candles.empty:

            return {

                "symbol": symbol,

                "saved": 0,

                "message": "No candles received"

            }


        saved = candle_repository.save_dataframe(

            db,

            candles,

            symbol,

            interval

        )


        return {

            "symbol": symbol,

            "saved": saved

        }



market_downloader = MarketDataDownloader()