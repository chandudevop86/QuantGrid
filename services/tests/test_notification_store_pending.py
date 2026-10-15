from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from Backend.application.notification_entity import NotificationEntity
from Backend.application.notification_store import (
    create_notification,
    get_retry_notifications,
)


def test_new_pending_notification_is_eligible_for_delivery():
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    try:
        with Session(engine) as db:
            notification = create_notification(
                db,
                channel="telegram",
                recipient="test-chat",
                subject="Critical protection alert",
                message="Broker-native stop-loss not verified",
            )

            due = get_retry_notifications(db, datetime.now(UTC))

            assert notification.status == "PENDING"
            assert [item.id for item in due] == [notification.id]
    finally:
        engine.dispose()
