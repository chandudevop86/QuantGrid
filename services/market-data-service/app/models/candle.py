from __future__ import annotations

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Text,
    PrimaryKeyConstraint,
)

from app.database.connection import Base


class Candle(Base):

    __tablename__ = "market_candles"


    symbol = Column(
        String(32),
        nullable=False
    )


    interval = Column(
        String(20),
        nullable=False
    )


    timestamp = Column(
        String(40),
        nullable=False
    )


    market_symbol = Column(
        String(64),
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
        Integer,
        nullable=True
    )


    source = Column(
        String(80),
        nullable=False
    )


    exchange_timezone = Column(
        String(80),
        nullable=True
    )


    stored_at = Column(
        String(40),
        nullable=False
    )


    payload_json = Column(
        Text,
        nullable=False
    )


    __table_args__ = (

        PrimaryKeyConstraint(
            "symbol",
            "interval",
            "timestamp"
        ),

    )