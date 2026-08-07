from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from Backend.core.database import Base


class NotificationEntity(Base):

    __tablename__ = "notifications"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    channel = Column(
        String(30),
        nullable=False,
        index=True,
    )

    recipient = Column(
        String(255),
        nullable=False,
    )

    subject = Column(
        String(255),
        nullable=False,
    )

    message = Column(
        Text,
        nullable=False,
    )

    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        index=True,
    )

    delivered = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    retries = Column(
        Integer,
        nullable=False,
        default=0,
    )

    error = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sent_at = Column(
        DateTime,
        nullable=True,
    )

    next_retry_at = Column(
        DateTime,
        nullable=True,
        index=True,
    )