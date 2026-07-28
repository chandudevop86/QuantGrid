from __future__ import annotations

import pandas as pd
from dhanhq import dhanhq

from app.config import settings


class DhanProvider:


    def __init__(self):

        self.client = None

        if settings.DHAN_ACCESS_TOKEN:

            self.client = dhanhq(
                access_token=settings.DHAN_ACCESS_TOKEN
            )


    def connected(self) -> bool:

        return self.client is not None



    def get_historical_candles(
        self,
        security_id: str,
        exchange_segment: str,
        timeframe: str,
        start_date: str,
        end_date: str

    ) -> pd.DataFrame:


        if not self.client:

            raise Exception(
                "Dhan access token missing"
            )


        try:

            # Dhan intraday candles
            response = self.client.intraday_minute_data(

                security_id=security_id,

                exchange_segment=exchange_segment,

                instrument_type="INDEX",

                interval=timeframe

            )


            if not response:

                return pd.DataFrame()


            data = response.get(
                "data",
                {}
            )


            df = pd.DataFrame(data)


            if df.empty:

                return df


            df.rename(
                columns={

                    "timestamp": "timestamp",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume"

                },
                inplace=True
            )


            if "timestamp" in df.columns:

                df["timestamp"] = pd.to_datetime(
                    df["timestamp"],
                    unit="s"
                )


            return df[
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume"
                ]
            ]


        except Exception as e:

            raise Exception(
                f"Dhan historical API failed: {e}"
            )



    def get_connection_status(self):

        return {

            "provider": "dhan",

            "connected": self.connected()

        }