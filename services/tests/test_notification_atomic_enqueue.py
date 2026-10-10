from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from Backend.application.notification_entity import NotificationEntity


def test_critical_batch_is_atomic_and_deduplicated():
    from Backend.application.notification_store import (
        enqueue_notifications_atomic,
    )

    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    destinations = [
        ("telegram", "test-chat"),
        ("slack", "configured"),
        ("email", "test@example.invalid"),
    ]

    try:
        with Session(engine) as db:
            for _ in range(2):
                enqueue_notifications_atomic(
                    db,
                    destinations=destinations,
                    subject="Critical protection failure",
                    message="TEST-BROKER-1 unprotected",
                    incident_key="test-incident-1",
                )
                db.commit()

            records = db.execute(
                select(NotificationEntity)
            ).scalars().all()

            assert len(records) == 3
            assert {record.channel for record in records} == {
                "telegram",
                "slack",
                "email",
            }
            assert all(record.status == "PENDING" for record in records)
            assert all(record.dedup_key for record in records)
            assert len({record.dedup_key for record in records}) == 3

        with Session(engine) as db:
            with pytest.raises(Exception):
                enqueue_notifications_atomic(
                    db,
                    destinations=[
                        ("telegram", "another-chat"),
                        ("email", None),
                    ],
                    subject="Critical protection failure",
                    message="TEST-BROKER-2 unprotected",
                    incident_key="test-incident-2",
                )

        with Session(engine) as db:
            records = db.execute(
                select(NotificationEntity)
            ).scalars().all()

            assert len(records) == 3

    finally:
        engine.dispose()


def test_atomic_enqueue_respects_caller_rollback():
    """Nested enqueue must never commit the caller's transaction."""
    from sqlalchemy import func

    from Backend.application.notification_store import (
        enqueue_notifications_atomic,
    )

    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    try:
        with Session(engine) as db:
            inserted = enqueue_notifications_atomic(
                db,
                destinations=[
                    ("telegram", "rollback-test-chat"),
                    ("slack", "configured"),
                    ("email", "rollback@example.invalid"),
                ],
                subject="Critical protection failure",
                message="TEST-ROLLBACK-REGRESSION",
                incident_key="rollback-regression-001",
            )

            assert inserted == 3
            db.rollback()

        with Session(engine) as db:
            remaining = db.scalar(
                select(func.count()).select_from(
                    NotificationEntity
                )
            )

            assert remaining == 0, (
                f"Caller rollback failed: "
                f"{remaining} notifications persisted"
            )

    finally:
        engine.dispose()


def test_atomic_enqueue_preserves_incident_key_boundaries():
    """Distinct tuples colliding under legacy encoding stay distinct."""
    from Backend.application.notification_store import (
        enqueue_notifications_atomic,
    )

    # Legacy separator was four literal characters, not a NUL byte.
    separator = "\\x00"

    first_incident = "incident"
    first_recipient = "part" + separator + "telegram" + separator + "end"

    second_incident = "incident" + separator + "telegram" + separator + "part"
    second_recipient = "end"

    old_first = separator.join(
        (first_incident, "telegram", first_recipient)
    )
    old_second = separator.join(
        (second_incident, "telegram", second_recipient)
    )

    assert (first_incident, first_recipient) != (
        second_incident, second_recipient
    )
    assert old_first == old_second, (
        "Test inputs must collide under legacy encoding"
    )

    engine = create_engine("sqlite:///:memory:")
    NotificationEntity.__table__.create(bind=engine)

    try:
        with Session(engine) as db:
            first = enqueue_notifications_atomic(
                db,
                destinations=[("telegram", first_recipient)],
                subject="Boundary test",
                message="First incident",
                incident_key=first_incident,
            )

            second = enqueue_notifications_atomic(
                db,
                destinations=[("telegram", second_recipient)],
                subject="Boundary test",
                message="Second incident",
                incident_key=second_incident,
            )

            db.commit()

            rows = db.scalars(
                select(NotificationEntity).order_by(
                    NotificationEntity.id
                )
            ).all()

            assert first == 1
            assert second == 1
            assert len(rows) == 2
            assert rows[0].dedup_key != rows[1].dedup_key

            print("PASS: legacy encoding collision reproduced")
            print("PASS: new encoding preserves tuple boundaries")

    finally:
        engine.dispose()
