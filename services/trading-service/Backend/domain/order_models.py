from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from Backend.core.database import Base


class OrderEntity(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    client_order_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    broker_order_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(
        String(30),
        index=True,
    )

    side: Mapped[str] = mapped_column(
        String(10),
    )

    quantity: Mapped[int] = mapped_column(Integer)

    filled_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    remaining_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    order_type: Mapped[str] = mapped_column(
        String(20),
        default="MARKET",
    )

    price: Mapped[float | None] = mapped_column(Float)

    average_price: Mapped[float | None] = mapped_column(Float)

    stop_loss: Mapped[float | None] = mapped_column(Float)

    target_price: Mapped[float | None] = mapped_column(Float)

    trailing_stop_loss: Mapped[float | None] = mapped_column(Float)

    trailing_stop_pct: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(
        String(20),
        default="NEW",
        index=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        String(300),
    )

    strategy: Mapped[str | None] = mapped_column(
        String(50),
    )

    exchange: Mapped[str | None] = mapped_column(
        String(20),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )