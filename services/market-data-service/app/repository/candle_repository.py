from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from sqlalchemy.orm import Session

from app.models.candle import Candle

from app.cache.redis_client import set_latest_candle

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
        try:
            db.flush()
        except Exception:
            db.rollback()
            existing = (
                db.query(Candle)
                .filter(
                    Candle.symbol == candle_data["symbol"],
                    Candle.interval == candle_data["interval"],
                    Candle.timestamp == candle_data["timestamp"],
                )
                .first()
            )
            return existing

        return candle

        

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


        # Ensure latest candle comes last
        df = df.sort_values(
            by="timestamp"
        ).reset_index(
            drop=True
        )


        for _, row in df.iterrows():

            candle = {

                "symbol": symbol,

                "interval": interval,

                "timestamp": str(
                    row["timestamp"]
                ),

                "market_symbol": symbol,

                "open": float(row["open"]),

                "high": float(row["high"]),

                "low": float(row["low"]),

                "close": float(row["close"]),

                "volume": int(
                    row.get("volume", 0)
                ),

                "source": "dhan"

            }
            

            self.save_candle(
                db,
                candle
            )

            saved += 1
            db.commit()
            try:
                    db.commit()
            except Exception:
                    db.rollback()
            raise

        # Update Redis with latest candle
        latest = df.iloc[-1]


        latest_candle = {

            "symbol": symbol,

            "interval": interval,

            "timestamp": str(
                latest["timestamp"]
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
                latest.get("volume", 0)
            ),

            "source": "dhan"

        }


        set_latest_candle(
            symbol,
            latest_candle
        )


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
    def get_latest_timestamp(
    self,
    db: Session,
    symbol: str,
    interval: str
    ):

        candle = (

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


        if not candle:
            return None


        return candle.timestamp


candle_repository = CandleRepository()