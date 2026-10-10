from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from Backend.application.notification_entity import NotificationEntity
from Backend.application.notification_store import create_notification


def test_only_one_worker_can_claim_pending_notification():
    from Backend.application.notification_store import claim_notification

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
            notification_id = notification.id

        with Session(engine) as first, Session(engine) as second:
            first_claim = claim_notification(
                first,
                notification_id,
                "worker-one",
                datetime.now(UTC),
            )
            second_claim = claim_notification(
                second,
                notification_id,
                "worker-two",
                datetime.now(UTC),
            )

            assert first_claim is True
            assert second_claim is False
    finally:
        engine.dispose()


def test_expired_notification_lease_can_be_reclaimed():
    from datetime import timedelta
    from Backend.application.notification_store import claim_notification

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
            notification_id = notification.id

        start = datetime.now(UTC)

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "worker-one", start,
                lease_seconds=120,
            )

        with Session(engine) as db:
            assert not claim_notification(
                db, notification_id, "worker-two",
                start + timedelta(seconds=60),
            )

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "worker-two",
                start + timedelta(seconds=121),
            )

            record = db.get(NotificationEntity, notification_id)
            assert record.status == "PROCESSING"
            assert record.claim_token == "worker-two"
    finally:
        engine.dispose()


def test_expired_worker_cannot_mark_new_owner_notification_sent():
    from datetime import timedelta
    from Backend.application.notification_store import (
        claim_notification,
        mark_sent,
    )

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
            notification_id = notification.id

        start = datetime.now(UTC)

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "worker-one", start, 120
            )
            assert claim_notification(
                db, notification_id, "worker-two",
                start + timedelta(seconds=121), 120
            )

            # Old owner must not overwrite the new owner's state.
            result = mark_sent(
                db,
                notification_id,
                claim_token="worker-one",
            )

            db.expire_all()
            record = db.get(NotificationEntity, notification_id)

            assert result is False
            assert record.status == "PROCESSING"
            assert record.claim_token == "worker-two"
            assert record.delivered is False
    finally:
        engine.dispose()


def test_current_owner_can_mark_notification_sent():
    from Backend.application.notification_store import (
        claim_notification,
        mark_sent,
    )

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
            notification_id = notification.id

        with Session(engine) as db:
            assert claim_notification(
                db,
                notification_id,
                "current-owner",
                datetime.now(UTC),
                lease_seconds=120,
            )

            assert mark_sent(
                db,
                notification_id,
                claim_token="current-owner",
            ) is True

            db.expire_all()
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "SENT"
            assert record.delivered is True
            assert record.claim_token is None
            assert record.lease_expires_at is None

    finally:
        engine.dispose()


def test_stale_worker_cannot_mark_notification_failed():
    from datetime import timedelta
    from Backend.application.notification_store import (
        claim_notification,
        mark_failed,
    )

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
            notification_id = notification.id

        start = datetime.now(UTC)

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "worker-one", start, 120
            )
            assert claim_notification(
                db, notification_id, "worker-two",
                start + timedelta(seconds=121), 120
            )

            assert mark_failed(
                db,
                notification_id,
                "stale worker failure",
                claim_token="worker-one",
            ) is False

            db.expire_all()
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "PROCESSING"
            assert record.claim_token == "worker-two"
            assert record.delivered is False
    finally:
        engine.dispose()


def test_stale_worker_cannot_schedule_retry():
    from datetime import timedelta
    from Backend.application.notification_store import (
        claim_notification,
        schedule_retry,
    )

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
            notification_id = notification.id

        start = datetime.now(UTC)

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "worker-one", start, 120
            )
            assert claim_notification(
                db, notification_id, "worker-two",
                start + timedelta(seconds=121), 120
            )

            assert schedule_retry(
                db,
                notification_id,
                "stale worker retry",
                claim_token="worker-one",
            ) is False

            db.expire_all()
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "PROCESSING"
            assert record.claim_token == "worker-two"
            assert record.retries == 0
            assert record.next_retry_at is None
    finally:
        engine.dispose()


def test_current_owner_can_mark_notification_failed():
    from Backend.application.notification_store import (
        claim_notification,
        mark_failed,
    )

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
            notification_id = notification.id

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "current-owner",
                datetime.now(UTC), 120,
            )

            assert mark_failed(
                db, notification_id,
                "provider rejected delivery",
                claim_token="current-owner",
            ) is True

            db.expire_all()
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "FAILED"
            assert record.delivered is False
            assert record.claim_token is None
            assert record.lease_expires_at is None
            assert record.error == "provider rejected delivery"
    finally:
        engine.dispose()


def test_current_owner_can_schedule_retry():
    from Backend.application.notification_store import (
        claim_notification,
        schedule_retry,
    )

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
            notification_id = notification.id

        with Session(engine) as db:
            assert claim_notification(
                db, notification_id, "current-owner",
                datetime.now(UTC), 120,
            )

            assert schedule_retry(
                db, notification_id,
                "temporary provider failure",
                claim_token="current-owner",
            ) is True

            db.expire_all()
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "RETRY"
            assert record.retries == 1
            assert record.next_retry_at is not None
            assert record.delivered is False
            assert record.claim_token is None
            assert record.lease_expires_at is None
    finally:
        engine.dispose()
