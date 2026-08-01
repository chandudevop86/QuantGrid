from __future__ import annotations

import os

from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from Backend.infrastructure.database.models.notification_entity import (
    NotificationEntity,
)

DEFAULT_RETRY_INTERVAL = int(
    os.getenv(
        "QUANTGRID_NOTIFICATION_RETRY_INTERVAL_SECONDS",
        "60",
    )
)


def create_notification(
    db: Session,
    *,
    channel: str,
    subject: str,
    message: str,
    recipient: str,
):

    obj = NotificationEntity(
        channel=channel,
        subject=subject,
        message=message,
        recipient=recipient,
        status="PENDING",
        retries=0,
        delivered=False,
        next_retry_at=None,
        error=None,
    )

    db.add(obj)
    db.commit()
    db.refresh(obj)

    return obj


def mark_sent(
    db: Session,
    notification_id: int,
):

    obj = db.get(
        NotificationEntity,
        notification_id,
    )

    if obj is None:
        return

    obj.status = "SENT"
    obj.sent_at = datetime.utcnow()
    obj.delivered = True
    obj.error = None
    obj.next_retry_at = None

    db.commit()


def mark_failed(
    db: Session,
    notification_id: int,
    error: str,
):

    obj = db.get(
        NotificationEntity,
        notification_id,
    )

    if obj is None:
        return

    obj.status = "FAILED"
    obj.error = error
    obj.delivered = False
    obj.next_retry_at = None

    db.commit()


def schedule_retry(
    db: Session,
    notification_id: int,
    error: str,
):

    obj = db.get(
        NotificationEntity,
        notification_id,
    )

    if obj is None:
        return

    obj.status = "RETRY"

    obj.error = error

    obj.delivered = False

    obj.retries += 1

    obj.next_retry_at = (
        datetime.utcnow()
        + timedelta(
            seconds=DEFAULT_RETRY_INTERVAL
        )
    )

    db.commit()


def get_retry_notifications(
    db: Session,
    now: datetime,
):

    return (
        db.query(NotificationEntity)
        .filter(
            and_(
                NotificationEntity.status == "RETRY",
                NotificationEntity.next_retry_at <= now,
            )
        )
        .all()
    )