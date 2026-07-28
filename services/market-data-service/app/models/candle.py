from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    UniqueConstraint
)

from app.database.connection import Base


class Candle(Base):

    __tablename__ = "market_candles"


    id = Column(
        Integer,
        primary_key=True,
        index=True
    )


    symbol = Column(
        String(50),
        nullable=False
    )


    exchange = Column(
        String(20),
        nullable=False
    )


    timeframe = Column(
        String(10),
        nullable=False
    )


    timestamp = Column(
        DateTime,
        nullable=False
    )


    open = Column(
        Float,
        nullable=False
    )


    high = Column(
        Float,
        nullable=False
    )


    low = Column(
        Float,
        nullable=False
    )


    close = Column(
        Float,
        nullable=False
    )


    volume = Column(
        Float,
        default=0
    )


    source = Column(
        String(30),
        default="dhan"
    )


    __table_args__ = (

        UniqueConstraint(
            "symbol",
            "timeframe",
            "timestamp"
        ),

    )