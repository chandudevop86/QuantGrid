from __future__ import annotations

import pandas as pd

from dhanhq import DhanContext, dhanhq

from app.config import settings


class DhanProvider:


    def __init__(self):

        self.client = None
        self.context = None


        if (
            settings.DHAN_CLIENT_ID
            and settings.DHAN_ACCESS_TOKEN
        ):

            self.context = DhanContext(
                settings.DHAN_CLIENT_ID,
                settings.DHAN_ACCESS_TOKEN
            )


            self.client = dhanhq(
                self.context
            )



    def connected(self) -> bool:

        return self.client is not None



    def get_connection_status(self):

        return {

            "provider": "dhan",

            "connected": self.connected()

        }



    def get_intraday_candles(
        self,
        security_id: str,
        exchange_segment: str,
        interval: str = "1"
    ) -> pd.DataFrame:


        if not self.client:

            raise Exception(
                "Dhan connection not initialized"
            )


        try:

            response = self.client.intraday_minute_data(

                security_id=security_id,

                exchange_segment=exchange_segment,

                instrument_type="INDEX",

                interval=interval

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


            if "timestamp" in df.columns:

                df["timestamp"] = pd.to_datetime(
                    df["timestamp"],
                    unit="s"
                )


            return df


        except Exception as e:

            raise Exception(
                f"Dhan intraday failed: {e}"
            )