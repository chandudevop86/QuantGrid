from __future__ import annotations

from sqlalchemy.orm import Session
import pandas as pd

from app.providers.dhan_provider import DhanProvider
from app.repository.candle_repository import candle_repository
from app.cache.redis_client import set_latest_candle


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


        # Get latest stored candle

        latest_timestamp = candle_repository.get_latest_timestamp(
            db,
            symbol,
            interval
        )


        # Initial database fill

        if latest_timestamp is None:

            print(
                f"{symbol}: Initial backfill"
            )

            from app.services.backfill_service import BackfillService

            BackfillService().backfill(
                db=db,
                symbol=symbol,
                security_id=security_id,
                exchange_segment=exchange_segment,
                interval=interval,
                days=365,
            )


            latest_timestamp = candle_repository.get_latest_timestamp(
                db,
                symbol,
                interval
            )


        # Fetch latest candles from Dhan

        candles = self.provider.get_intraday_candles(

            security_id=security_id,

            exchange_segment=exchange_segment,

            interval=interval,

            latest_timestamp=latest_timestamp
        )


        if candles.empty:

            print(
                f"{symbol}: No candles received"
            )

            return {

                "symbol": symbol,

                "saved": 0,

                "source": "dhan",

                "message": "No candles received"

            }



        # Normalize timestamps to UTC

        candles["timestamp"] = pd.to_datetime(
            candles["timestamp"],
            utc=True
        )


        if latest_timestamp is not None:


            latest_timestamp = pd.to_datetime(
                latest_timestamp,
                utc=True
            )


            candles = candles[
                candles["timestamp"] > latest_timestamp
            ]



        if candles.empty:

            print(
                f"{symbol}: Already up to date"
            )

            return {

                "symbol": symbol,

                "saved": 0,

                "message": "Already up to date",

                "latest": str(latest_timestamp),

                "source": "dhan"

            }



        # Remove duplicate timestamps

        candles = (

            candles

            .sort_values(
                "timestamp"
            )

            .drop_duplicates(
                subset=[
                    "timestamp"
                ]
            )

            .reset_index(
                drop=True
            )

        )



        # Save database

        saved = candle_repository.save_dataframe(

            db,

            candles,

            symbol,

            interval

        )



        # Latest candle for Redis

        latest = candles.iloc[-1]


        redis_candle = {

            "symbol": symbol,

            "interval": interval,


            "timestamp": str(

                pd.to_datetime(

                    latest["timestamp"],

                    utc=True

                )

                .tz_convert(
                    "Asia/Kolkata"
                )

            ),


            "open": float(
                latest["open"]
            ),


            "high": float(
                latest["high"]
            ),


            "low": float(
                latest["low"]
            ),


            "close": float(
                latest["close"]
            ),


            "volume": int(
                latest.get(
                    "volume",
                    0
                )
            ),


            "source": "dhan"

        }



        set_latest_candle(

            symbol,

            redis_candle

        )



        return {

            "symbol": symbol,

            "saved": saved,

            "latest": str(
                latest["timestamp"]
            ),

            "source": "dhan"

        }



market_downloader = MarketDataDownloader()