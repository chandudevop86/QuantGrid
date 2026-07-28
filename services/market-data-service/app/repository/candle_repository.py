from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from sqlalchemy.orm import Session

from app.models.candle import Candle



class CandleRepository:


    def save_candle(
        self,
        db: Session,
        candle_data: dict
    ):

        existing = (

            db.query(Candle)

            .filter(

                Candle.symbol == candle_data["symbol"],

                Candle.interval == candle_data["interval"],

                Candle.timestamp == candle_data["timestamp"]

            )

            .first()

        )


        if existing:

            return existing



        candle = Candle(

            symbol=candle_data["symbol"],


            interval=candle_data["interval"],


            timestamp=candle_data["timestamp"],


            market_symbol=candle_data.get(
                "market_symbol",
                candle_data["symbol"]
            ),


            open=float(
                candle_data["open"]
            ),


            high=float(
                candle_data["high"]
            ),


            low=float(
                candle_data["low"]
            ),


            close=float(
                candle_data["close"]
            ),


            volume=int(
                candle_data.get(
                    "volume",
                    0
                )
            ),


            source=candle_data.get(
                "source",
                "dhan"
            ),


            exchange_timezone="Asia/Kolkata",


            stored_at=datetime.now(
                timezone.utc
            ).isoformat(),


            payload_json=json.dumps(
                candle_data,
                default=str
            )

        )


        db.add(candle)

        db.commit()

        db.refresh(candle)


        return candle



    def save_dataframe(
        self,
        db: Session,
        df: pd.DataFrame,
        symbol: str,
        interval: str
    ):

        saved = 0


        for _, row in df.iterrows():


            candle = {

                "symbol": symbol,

                "interval": interval,

                "timestamp": str(
                    row["timestamp"]
                ),


                "market_symbol": symbol,


                "open": row["open"],


                "high": row["high"],


                "low": row["low"],


                "close": row["close"],


                "volume": row.get(
                    "volume",
                    0
                ),


                "source": "dhan"

            }


            self.save_candle(
                db,
                candle
            )


            saved += 1



        return saved



    def get_latest(
        self,
        db: Session,
        symbol: str,
        interval: str
    ):


        return (

            db.query(Candle)

            .filter(

                Candle.symbol == symbol,

                Candle.interval == interval

            )

            .order_by(

                Candle.timestamp.desc()

            )

            .first()

        )



    def get_history(
        self,
        db: Session,
        symbol: str,
        interval: str,
        limit: int = 500
    ):


        return (

            db.query(Candle)

            .filter(

                Candle.symbol == symbol,

                Candle.interval == interval

            )

            .order_by(

                Candle.timestamp.desc()

            )

            .limit(limit)

            .all()

        )



candle_repository = CandleRepository()