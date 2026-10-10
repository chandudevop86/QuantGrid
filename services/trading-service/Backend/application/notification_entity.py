from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Index,
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

    __table_args__ = (
        Index("uq_notifications_dedup_key", "dedup_key", unique=True),
    )

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

    # NULL permits ordinary notifications without deduplication.
    # Critical reconciliation alerts use a stable episode-specific key.
    dedup_key = Column(
        String(160),
        nullable=True,
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
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    sent_at = Column(
        DateTime,
        nullable=True,
    )

    claim_token = Column(
        String(80),
        nullable=True,
    )

    lease_expires_at = Column(
        DateTime,
        nullable=True,
        index=True,
    )

    next_retry_at = Column(
        DateTime,
        nullable=True,
        index=True,
    )