"""Regression tests for durable LIVE protection-alert episodes."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_repeated_failure_reuses_active_episode():
    from Backend.application.protection_alert_episodes import (
        open_protection_failure_episode,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")

    from Backend.application.protection_alert_episodes import (
        ProtectionAlertEpisode,
    )
    ProtectionAlertEpisode.__table__.create(engine)

    with Session(engine) as db:
        first = open_protection_failure_episode(
            db,
            local_order_id="TEST-ORDER-001",
        )
        db.commit()

        second = open_protection_failure_episode(
            db,
            local_order_id="TEST-ORDER-001",
        )
        db.commit()

        assert first == second


def test_recovery_allows_new_failure_episode():
    from Backend.application.protection_alert_episodes import (
        close_protection_failure_episode,
        open_protection_failure_episode,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")

    from Backend.application.protection_alert_episodes import (
        ProtectionAlertEpisode,
    )
    ProtectionAlertEpisode.__table__.create(engine)

    with Session(engine) as db:
        first = open_protection_failure_episode(
            db,
            local_order_id="TEST-ORDER-002",
        )
        db.commit()

        close_protection_failure_episode(
            db,
            local_order_id="TEST-ORDER-002",
        )
        db.commit()

        second = open_protection_failure_episode(
            db,
            local_order_id="TEST-ORDER-002",
        )
        db.commit()

        assert first != second
