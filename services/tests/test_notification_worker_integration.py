from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from Backend.application import notification_retry
from Backend.application.notification_entity import NotificationEntity
from Backend.application.notification_store import create_notification


def test_worker_claims_and_delivers_pending_notification(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    delivered = []

    def fake_send(channel, recipient, subject, message):
        delivered.append((channel, recipient, subject, message))

    monkeypatch.setattr(
        notification_retry,
        "send_notification_channel",
        fake_send,
    )

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
            worker = notification_retry.NotificationRetryWorker(db)
            result = asyncio.run(worker.run())

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "SENT"
            assert record.delivered is True
            assert record.claim_token is None
            assert record.lease_expires_at is None
            assert record.sent_at is not None

        assert delivered == [
            (
                "telegram",
                "test-chat",
                "Critical protection alert",
                "Broker-native stop-loss not verified",
            )
        ]
        assert result["processed"] == 1
        assert result["succeeded"] == 1

    finally:
        engine.dispose()


def test_worker_schedules_retry_after_provider_failure(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    attempts = []

    def fake_send(channel, recipient, subject, message):
        attempts.append(channel)
        raise RuntimeError("Simulated provider failure")

    monkeypatch.setattr(
        notification_retry,
        "send_notification_channel",
        fake_send,
    )

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
            worker = notification_retry.NotificationRetryWorker(db)
            result = asyncio.run(worker.run())

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "RETRY"
            assert record.delivered is False
            assert record.retries == 1
            assert record.next_retry_at is not None
            assert record.sent_at is None
            assert record.claim_token is None
            assert record.lease_expires_at is None

        assert attempts == ["telegram"]
        assert result["processed"] == 1
        assert result["succeeded"] == 0
        assert result["retry_scheduled"] == 1

    finally:
        engine.dispose()


def test_worker_permanently_fails_after_max_retries(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    attempts = []

    def fake_send(channel, recipient, subject, message):
        attempts.append(channel)
        raise RuntimeError("Simulated provider failure")

    monkeypatch.setattr(
        notification_retry,
        "send_notification_channel",
        fake_send,
    )

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
            notification.retries = 4
            db.commit()

        with Session(engine) as db:
            worker = notification_retry.NotificationRetryWorker(db)
            worker.max_retries = 5
            result = asyncio.run(worker.run())

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "FAILED"
            assert record.delivered is False
            assert record.retries == 4
            assert record.sent_at is None
            assert record.next_retry_at is None
            assert record.claim_token is None
            assert record.lease_expires_at is None

        assert attempts == ["telegram"]
        assert result["processed"] == 1
        assert result["succeeded"] == 0
        assert result["retry_scheduled"] == 0
        assert result["permanently_failed"] == 1

    finally:
        engine.dispose()


def test_worker_recovers_expired_processing_lease(monkeypatch):
    from datetime import UTC, datetime, timedelta

    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    delivered = []

    def fake_send(channel, recipient, subject, message):
        delivered.append(channel)

    monkeypatch.setattr(
        notification_retry,
        "send_notification_channel",
        fake_send,
    )

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

            notification.status = "PROCESSING"
            notification.claim_token = "abandoned-worker-token"
            notification.lease_expires_at = (
                datetime.now(UTC) - timedelta(minutes=5)
            )

            db.commit()

        with Session(engine) as db:
            worker = notification_retry.NotificationRetryWorker(db)
            result = asyncio.run(worker.run())

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "SENT"
            assert record.delivered is True
            assert record.claim_token is None
            assert record.lease_expires_at is None
            assert record.sent_at is not None

        assert delivered == ["telegram"]
        assert result["processed"] == 1
        assert result["succeeded"] == 1

    finally:
        engine.dispose()


def test_worker_does_not_leak_provider_secrets(monkeypatch, caplog):
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    fake_token = "FAKE_TELEGRAM_SECRET_123456"
    fake_webhook = (
        "https://hooks.slack.com/services/"
        "FAKE_WORKSPACE/FAKE_CHANNEL/FAKE_SECRET"
    )

    def fake_send(channel, recipient, subject, message):
        raise RuntimeError(
            f"Provider failed: {fake_token} {fake_webhook}"
        )

    monkeypatch.setattr(
        notification_retry,
        "send_notification_channel",
        fake_send,
    )

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
            worker = notification_retry.NotificationRetryWorker(db)
            result = asyncio.run(worker.run())

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)

            assert record.status == "RETRY"
            assert record.error == (
                "notification_delivery_provider_failure"
            )

            assert fake_token not in record.error
            assert fake_webhook not in record.error

        assert fake_token not in caplog.text
        assert fake_webhook not in caplog.text
        assert result["retry_scheduled"] == 1

    finally:
        engine.dispose()


def test_worker_does_not_retry_as_provider_failure_after_sent_db_error(monkeypatch):
    """A database failure after provider acceptance is not a send failure."""
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    delivered = []
    retry_calls = []

    def fake_send(channel, recipient, subject, message):
        delivered.append(channel)

    def broken_mark_sent(*args, **kwargs):
        raise RuntimeError("Simulated database status-update failure")

    def track_retry(*args, **kwargs):
        retry_calls.append(True)
        return True

    monkeypatch.setattr(
        notification_retry, "send_notification_channel", fake_send
    )
    monkeypatch.setattr(
        notification_retry, "mark_sent", broken_mark_sent
    )
    monkeypatch.setattr(
        notification_retry, "schedule_retry", track_retry
    )

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
            worker = notification_retry.NotificationRetryWorker(db)
            try:
                asyncio.run(worker.run())
            except RuntimeError:
                pass

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)
            assert record.status == "PROCESSING"

        assert delivered == ["telegram"]
        assert retry_calls == [], (
            "Database status-update failure was incorrectly handled "
            "as a provider delivery failure"
        )

    finally:
        engine.dispose()



def test_worker_rolls_back_when_retry_database_update_fails(monkeypatch):
    """A retry persistence failure must roll back the worker session."""
    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    attempts = []

    def fake_send(channel, recipient, subject, message):
        attempts.append(channel)
        raise RuntimeError("Simulated provider failure")

    def broken_schedule_retry(db, notification_id, error, *, claim_token):
        # Simulate a database operation that fails after entering
        # a transaction, before retry status can be persisted.
        db.get(NotificationEntity, notification_id)
        raise RuntimeError("Simulated retry database failure")

    monkeypatch.setattr(
        notification_retry,
        "send_notification_channel",
        fake_send,
    )
    monkeypatch.setattr(
        notification_retry,
        "schedule_retry",
        broken_schedule_retry,
    )

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
            rollback_calls = []
            original_rollback = db.rollback

            def track_rollback():
                rollback_calls.append(True)
                return original_rollback()

            monkeypatch.setattr(db, "rollback", track_rollback)

            worker = notification_retry.NotificationRetryWorker(db)

            try:
                asyncio.run(worker.run())
            except RuntimeError as exc:
                assert str(exc) == "Simulated retry database failure"
            else:
                raise AssertionError("Expected retry database failure")

            assert rollback_calls, (
                "Worker did not roll back after retry database failure"
            )

        with Session(engine) as db:
            record = db.get(NotificationEntity, notification_id)
            assert record.status == "PROCESSING"

        assert attempts == ["telegram"]

    finally:
        engine.dispose()
