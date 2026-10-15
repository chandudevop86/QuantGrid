from __future__ import annotations

from sqlalchemy import select

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def test_critical_live_protection_alert_is_persisted(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation
    from Backend.application.notification_entity import NotificationEntity
    from Backend.core.database import SessionLocal
    from Backend.domain.security.models import User

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    # No external notification should be sent during this test.
    monkeypatch.setattr(
        broker_reconciliation,
        "send_alert",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    with SessionLocal() as db:
        actor = User(
            username="durable-alert-test",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = {"mismatches": 0, "needs_review": 0}

        broker_reconciliation._record_review(
            summary,
            db,
            actor,
            None,
            "live_filled_exposure_not_broker_protected",
            "TEST-BROKER-NO-STOP",
            {"source": "isolated_test"},
        )

        records = db.execute(
            select(NotificationEntity).where(
                NotificationEntity.subject.like(
                    "%LIVE position protection failure%"
                )
            )
        ).scalars().all()

        assert summary["needs_review"] == 1
        assert len(records) >= 1
        assert all(record.status == "PENDING" for record in records)
        assert any(
            "TEST-BROKER-NO-STOP" in record.message
            for record in records
        )



def test_slack_webhook_secret_is_not_persisted(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation
    from Backend.application.notification_entity import NotificationEntity
    from Backend.core.database import SessionLocal
    from Backend.domain.security.models import User

    fake_webhook = (
        "https://hooks.slack.com/services/"
        "TEST/NOT-REAL/SECRET-MUST-NOT-BE-STORED"
    )

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", fake_webhook)

    with SessionLocal() as db:
        actor = User(
            username="slack-secret-test",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = {"mismatches": 0, "needs_review": 0}

        broker_reconciliation._record_review(
            summary,
            db,
            actor,
            None,
            "live_filled_exposure_not_broker_protected",
            "TEST-SLACK-NO-STOP",
            {"source": "isolated_test"},
        )

        records = db.query(NotificationEntity).filter(
            NotificationEntity.channel == "slack"
        ).all()

        assert summary["needs_review"] == 1
        assert len(records) == 1

        record = records[0]
        assert record.status == "PENDING"
        assert record.recipient == "configured"

        for value in (
            record.recipient,
            record.subject,
            record.message,
            record.error or "",
        ):
            assert fake_webhook not in value



def test_repeated_live_protection_review_does_not_duplicate_alert(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation
    from Backend.application.notification_entity import NotificationEntity
    from Backend.core.database import SessionLocal
    from Backend.domain.security.models import User

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    with SessionLocal() as db:
        actor = User(
            username="dedup-alert-test",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = {"mismatches": 0, "needs_review": 0}

        for _ in range(2):
            broker_reconciliation._record_review(
                summary,
                db,
                actor,
                None,
                "live_filled_exposure_not_broker_protected",
                "TEST-SAME-EXPOSURE",
                {"source": "isolated_test"},
            )

        records = db.query(NotificationEntity).filter(
            NotificationEntity.channel == "telegram",
            NotificationEntity.message.like("%TEST-SAME-EXPOSURE%"),
        ).all()

        assert summary["needs_review"] == 2
        assert len(records) == 1
        assert records[0].status == "PENDING"
