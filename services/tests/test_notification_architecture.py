from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "trading-service"


def test_legacy_notification_prototype_is_removed():
    obsolete = [
        "Backend/infrastructure/container.py",
        "Backend/infrastructure/database/postgres_notification_repository.py",
        "Backend/application/notification_service.py",
        "Backend/application/events/order_event_publisher.py",
        "Backend/domain/notifications/models.py",
        "Backend/domain/notifications/repository.py",
        "Backend/domain/notifications/notification_repo.py",
        "Backend/domain/events/trading_events.py",
        "test_notification.py",
    ]

    for relative in obsolete:
        assert not (SERVICE / relative).exists(), relative


def test_active_notification_pipeline_remains_versioned_and_worker_backed():
    required = [
        "Backend/application/notification_store.py",
        "Backend/application/worker.py",
        "Backend/presentation/api/notifications_api.py",
        "Backend/core/schema_migrations.py",
    ]

    for relative in required:
        assert (SERVICE / relative).exists(), relative

    migrations = (SERVICE / "Backend/core/schema_migrations.py").read_text(encoding="utf-8")
    assert "NOTIFICATION_DELIVERY_LEASES_VERSION" in migrations
    assert "NOTIFICATION_DEDUPLICATION_VERSION" in migrations
    assert "CREATE TABLE IF NOT EXISTS notifications (" in migrations

    worker = (SERVICE / "Backend/application/worker.py").read_text(encoding="utf-8")
    assert '"notification"' in worker
    assert '"notification-retry"' in worker
