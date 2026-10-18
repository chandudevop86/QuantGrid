"""Atomic protection episode and notification regression tests."""

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from Backend.application.notification_entity import NotificationEntity
from Backend.application.notification_store import enqueue_notifications_atomic
from Backend.application.protection_alert_episodes import (
    ProtectionAlertEpisode,
    close_protection_failure_episode,
    open_protection_failure_episode,
)


DESTINATIONS = [
    ("telegram", "episode-test-chat"),
    ("slack", "configured"),
    ("email", "episode@example.invalid"),
]


def _create_tables(engine):
    ProtectionAlertEpisode.__table__.create(engine)
    NotificationEntity.__table__.create(engine)


def _stage_failure(db, local_order_id):
    episode_id = open_protection_failure_episode(
        db,
        local_order_id=local_order_id,
    )
    inserted = enqueue_notifications_atomic(
        db,
        destinations=DESTINATIONS,
        subject="Critical LIVE protection failure",
        message=f"Unprotected exposure: {local_order_id}",
        incident_key=episode_id,
    )
    return episode_id, inserted


def test_repeated_failure_and_verified_recovery():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        _create_tables(engine)

        with Session(engine) as db:
            first, inserted = _stage_failure(db, "ORDER-EPISODE-1")
            assert inserted == 3
            db.commit()

            repeated, inserted = _stage_failure(db, "ORDER-EPISODE-1")
            assert repeated == first
            assert inserted == 0
            db.commit()

            assert close_protection_failure_episode(
                db,
                local_order_id="ORDER-EPISODE-1",
            ) == 1
            db.commit()

            second, inserted = _stage_failure(db, "ORDER-EPISODE-1")
            assert second != first
            assert inserted == 3
            db.commit()

            episodes = db.scalars(
                select(ProtectionAlertEpisode)
            ).all()
            notifications = db.scalars(
                select(NotificationEntity)
            ).all()

            assert len(episodes) == 2
            assert sum(e.closed_at is None for e in episodes) == 1
            assert len(notifications) == 6
            assert len({n.dedup_key for n in notifications}) == 6

    finally:
        engine.dispose()


def test_rollback_removes_episode_and_notifications():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        _create_tables(engine)

        with Session(engine) as db:
            _, inserted = _stage_failure(db, "ORDER-ROLLBACK-1")
            assert inserted == 3
            db.rollback()

        with Session(engine) as db:
            episode_count = db.scalar(
                select(func.count()).select_from(
                    ProtectionAlertEpisode
                )
            )
            notification_count = db.scalar(
                select(func.count()).select_from(
                    NotificationEntity
                )
            )

            assert episode_count == 0
            assert notification_count == 0

    finally:
        engine.dispose()



def test_protection_failure_persists_episode_without_notification_destinations(monkeypatch):
    from test_sqlalchemy_trading_stores import configure_sqlalchemy_store

    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation
    from Backend.application.notification_entity import NotificationEntity
    from Backend.application.protection_alert_episodes import ProtectionAlertEpisode
    from Backend.core.database import SessionLocal
    from Backend.domain.security.models import User

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "false")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_TO", raising=False)

    with SessionLocal() as db:
        actor = User(
            username="no-destination-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()

        for _ in range(2):
            broker_reconciliation._record_review(
                {
                    "mismatches": 0,
                    "needs_review": 0,
                },
                db,
                actor,
                None,
                "live_filled_exposure_not_broker_protected",
                "DHAN-NO-DESTINATION",
                {
                    "local_order": {
                        "local_order_id": "ORD-NO-DESTINATION",
                    },
                },
            )

    with SessionLocal() as db:
        episodes = (
            db.query(ProtectionAlertEpisode)
            .filter(
                ProtectionAlertEpisode.local_order_id
                == "ORD-NO-DESTINATION"
            )
            .all()
        )

        assert len(episodes) == 1
        assert episodes[0].closed_at is None
        assert db.query(NotificationEntity).count() == 0
