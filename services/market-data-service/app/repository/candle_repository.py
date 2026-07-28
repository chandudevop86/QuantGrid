from __future__ import annotations

from datetime import datetime

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
                Candle.timeframe == candle_data["timeframe"],
                Candle.timestamp == candle_data["timestamp"]
            )
            .first()
        )


        if existing:

            return existing



        candle = Candle(

            symbol=candle_data["symbol"],

            exchange=candle_data["exchange"],

            timeframe=candle_data["timeframe"],

            timestamp=candle_data["timestamp"],

            open=candle_data["open"],

            high=candle_data["high"],

            low=candle_data["low"],

            close=candle_data["close"],

            volume=candle_data.get(
                "volume",
                0
            ),

            source=candle_data.get(
                "source",
                "dhan"
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
        exchange: str,
        timeframe: str
    ):


        saved = 0


        for _, row in df.iterrows():


            candle = {

                "symbol": symbol,

                "exchange": exchange,

                "timeframe": timeframe,

                "timestamp": row["timestamp"],

                "open": float(row["open"]),

                "high": float(row["high"]),

                "low": float(row["low"]),

                "close": float(row["close"]),

                "volume": float(
                    row.get(
                        "volume",
                        0
                    )
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
        timeframe: str
    ):


        return (

            db.query(Candle)

            .filter(
                Candle.symbol == symbol,

                Candle.timeframe == timeframe
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
        timeframe: str,
        limit: int = 500
    ):


        return (

            db.query(Candle)

            .filter(

                Candle.symbol == symbol,

                Candle.timeframe == timeframe

            )

            .order_by(

                Candle.timestamp.desc()

            )

            .limit(limit)

            .all()

        )



candle_repository = CandleRepository()
