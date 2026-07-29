from __future__ import annotations

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Text,
    DateTime,
    PrimaryKeyConstraint,
)

from app.database.connection import Base


class Candle(Base):

    __tablename__ = "market_candles"

    symbol = Column(
        String(32),
        nullable=False,
        index=True,
    )

    interval = Column(
        String(20),
        nullable=False,
        index=True,
    )

    # Market candle timestamp (IST)
    timestamp = Column(
        DateTime(timezone=False),
        nullable=False,
        index=True,
    )

    market_symbol = Column(
        String(64),
        nullable=False,
    )

    open = Column(
        Float,
        nullable=False,
    )

    high = Column(
        Float,
        nullable=False,
    )

    low = Column(
        Float,
        nullable=False,
    )

    close = Column(
        Float,
        nullable=False,
    )

    volume = Column(
        Integer,
        nullable=False,
        default=0,
    )

    source = Column(
        String(80),
        nullable=False,
        default="dhan",
    )

    exchange_timezone = Column(
        String(80),
        nullable=False,
        default="Asia/Kolkata",
    )

    # Record insertion time
    stored_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    payload_json = Column(
        Text,
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "symbol",
            "interval",
            "timestamp",
        ),
    )