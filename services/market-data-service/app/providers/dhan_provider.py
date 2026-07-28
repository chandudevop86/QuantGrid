from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from dhanhq import dhanhq

from app.config import settings


class DhanProvider:


    def __init__(self):

        self.client = None

        if (
            settings.DHAN_CLIENT_ID
            and settings.DHAN_ACCESS_TOKEN
        ):

            self.client = dhanhq(
                settings.DHAN_CLIENT_ID,
                settings.DHAN_ACCESS_TOKEN
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
                "Dhan credentials missing"
            )


        try:

            response = self.client.historical_daily_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type="EQUITY",
                from_date=start_date,
                to_date=end_date
            )


            if not response:

                return pd.DataFrame()



            candles = response.get(
                "data",
                {}
            )


            df = pd.DataFrame(candles)


            if df.empty:

                return df



            df.rename(
                columns={
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                    "timestamp": "timestamp"
                },
                inplace=True
            )


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

            "connected":
            self.connected()

        }