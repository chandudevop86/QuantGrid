from datetime import datetime

from sqlalchemy.orm import Session

from Backend.infrastructure.database.models.notification_entity import (
    NotificationEntity,
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

    obj.status = "SENT"
    obj.sent_at = datetime.utcnow()
    obj.delivered = True

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

    obj.status = "FAILED"
    obj.error = error
    obj.retries += 1

    db.commit()