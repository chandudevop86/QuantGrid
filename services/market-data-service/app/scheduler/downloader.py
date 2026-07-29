from __future__ import annotations

from sqlalchemy.orm import Session
import pandas as pd
from app.providers.dhan_provider import DhanProvider
from app.repository.candle_repository import candle_repository
from app.cache.redis_client import set_latest_candle
from zoneinfo import ZoneInfo




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

        latest_timestamp = candle_repository.get_latest_timestamp(
            db,
            symbol,
            interval
        )
        if latest_timestamp is None:

            print(f"{symbol}: Initial backfill")

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
        candles = self.provider.get_intraday_candles(

            security_id=security_id,

            exchange_segment=exchange_segment,

            interval=interval,
            
            latest_timestamp=latest_timestamp
        )


        if candles.empty:
            print(f"{symbol}: already up to date")
            return {

                "symbol": symbol,

                "saved": 0,
                "source": "dhan",
                "message": "No candles received"

            }
        if latest_timestamp is not None:

            latest_timestamp = pd.to_datetime(
                latest_timestamp,
                utc=True
            )

            candles["timestamp"] = pd.to_datetime(
                candles["timestamp"],
                utc=True
            )

            candles = candles[
                candles["timestamp"] > latest_timestamp
            ]

        if candles.empty:
            print(f"{symbol}: Already up to date")
            return {
                "symbol": symbol,
                "saved": 0,
                "message": "Already up to date",
                "latest": str(latest_timestamp),
                "source": "dhan"
            }


        saved = candle_repository.save_dataframe(
            db,
            candles,
            symbol,
            interval
        )


        # Store latest candle in Redis

        candles = candles.sort_values(
            by="timestamp"
        ).reset_index(
            drop=True
        )


        latest = candles.iloc[-1]


        set_latest_candle(

            symbol,

            {
                "symbol": symbol,

                "interval": interval,

                "timestamp": str(
                    latest["timestamp"]
                    .tz_convert(
                        ZoneInfo("Asia/Kolkata")
                    )
                    if latest["timestamp"].tzinfo
                    else latest["timestamp"]
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
                    latest["volume"]
                ),

                "source": "dhan"

            }

        )


        return {
            "symbol": symbol,
            "saved": saved,
            "latest": str(latest["timestamp"]),
            "source": "dhan"
}


market_downloader = MarketDataDownloader()