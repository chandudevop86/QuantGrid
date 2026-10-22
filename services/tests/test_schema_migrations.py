from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect


def test_postgres_migrations_lock_before_schema_inspection(monkeypatch):
    from Backend.core import schema_migrations

    events: list[str] = []
    connection = MagicMock()
    connection.execute.side_effect = lambda *args, **kwargs: events.append("lock")
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine = MagicMock()
    engine.dialect = SimpleNamespace(name="postgresql")
    engine.begin.return_value = transaction

    inspector = MagicMock()
    inspector.get_table_names.side_effect = lambda: events.append("inspect") or []
    monkeypatch.setattr(schema_migrations, "inspect", lambda bind: inspector)

    schema_migrations.apply_compatibility_migrations(engine, ("audit_logs",))

    assert events == ["lock", "inspect"]
    statement, parameters = connection.execute.call_args.args
    assert str(statement) == "SELECT pg_advisory_xact_lock(:lock_id)"
    assert parameters == {"lock_id": schema_migrations.POSTGRES_MIGRATION_LOCK_ID}


def test_versioned_migrations_record_baseline_and_compatibility():
    from Backend.core import schema_migrations

    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    Table("orders", metadata, Column("id", Integer, primary_key=True))

    schema_migrations.apply_versioned_migrations(engine, metadata)
    schema_migrations.apply_versioned_migrations(engine, metadata)

    with engine.connect() as connection:
        versions = connection.execute(
            schema_migrations.text(
                f"SELECT version FROM {schema_migrations.MIGRATION_TABLE} ORDER BY version"
            )
        ).scalars().all()
    assert versions == [
        schema_migrations.BASELINE_VERSION,
        schema_migrations.COMPATIBILITY_VERSION,
        schema_migrations.SUBSCRIPTION_ENTITLEMENTS_VERSION,
        schema_migrations.INSTITUTIONAL_METRICS_VERSION,
        schema_migrations.PAPER_TRADE_COST_EVIDENCE_VERSION,
        schema_migrations.BROKER_SUBMISSION_INTENTS_VERSION,
        schema_migrations.POSITION_EXECUTION_MODE_VERSION,
        schema_migrations.NOTIFICATION_DELIVERY_LEASES_VERSION,
        schema_migrations.NOTIFICATION_DEDUPLICATION_VERSION,
        schema_migrations.PROTECTION_ALERT_EPISODES_VERSION,
        schema_migrations.SIGNAL_EVALUATION_EVENTS_VERSION,
    ]
    inspector = inspect(engine)
    assert "signal_evaluation_events" in inspector.get_table_names()
    assert "execution_mode" in {column["name"] for column in inspector.get_columns("orders")}

    assert "broker_submission_intents" in inspector.get_table_names()

    intent_columns = {
        column["name"]
        for column in inspector.get_columns("broker_submission_intents")
    }
    assert {
        "local_order_id",
        "logical_key",
        "correlation_id",
        "broker_order_id",
        "status",
        "created_at",
        "updated_at",
    } <= intent_columns

    intent_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("broker_submission_intents")
    }
    assert "uq_broker_submission_intents_active_key" in intent_indexes
    assert intent_indexes["uq_broker_submission_intents_active_key"]["unique"]
    assert "uq_broker_submission_intents_broker_id" in intent_indexes
    assert intent_indexes["uq_broker_submission_intents_broker_id"]["unique"]



def test_cost_evidence_migration_runs_for_existing_compatibility_database():
    from Backend.core import schema_migrations

    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()

    with engine.begin() as connection:
        connection.execute(schema_migrations.text(
            "CREATE TABLE trade_journal (id INTEGER PRIMARY KEY)"
        ))
        connection.execute(schema_migrations.text(
            f"CREATE TABLE {schema_migrations.MIGRATION_TABLE} ("
            "version VARCHAR(80) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)"
        ))
        for version in (
            schema_migrations.BASELINE_VERSION,
            schema_migrations.COMPATIBILITY_VERSION,
            schema_migrations.SUBSCRIPTION_ENTITLEMENTS_VERSION,
            schema_migrations.INSTITUTIONAL_METRICS_VERSION,
        ):
            connection.execute(
                schema_migrations.text(
                    f"INSERT INTO {schema_migrations.MIGRATION_TABLE} (version) VALUES (:version)"
                ),
                {"version": version},
            )

    schema_migrations.apply_versioned_migrations(engine, metadata)

    columns = {column["name"] for column in inspect(engine).get_columns("trade_journal")}
    assert {"gross_pnl", "total_costs", "net_pnl", "broker_order_id"} <= columns

    with engine.connect() as connection:
        versions = set(connection.execute(
            schema_migrations.text(
                f"SELECT version FROM {schema_migrations.MIGRATION_TABLE}"
            )
        ).scalars())
    assert schema_migrations.PAPER_TRADE_COST_EVIDENCE_VERSION in versions


def test_notification_migration_creates_missing_table():
    from Backend.core import schema_migrations
    from Backend.application.notification_entity import NotificationEntity

    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()

    try:
        # Simulate an established deployment with a migration ledger
        # but no notifications table.
        with engine.begin() as connection:
            connection.execute(schema_migrations.text(
                f"CREATE TABLE {schema_migrations.MIGRATION_TABLE} ("
                "version VARCHAR(80) PRIMARY KEY, "
                "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            ))

        schema_migrations.apply_versioned_migrations(engine, metadata)
        schema_migrations.apply_versioned_migrations(engine, metadata)

        columns = {
            column["name"]
            for column in inspect(engine).get_columns("notifications")
        }

        assert set(NotificationEntity.__table__.columns.keys()) <= columns

        with engine.connect() as connection:
            versions = connection.execute(schema_migrations.text(
                f"SELECT version FROM {schema_migrations.MIGRATION_TABLE} "
                "WHERE version = '0009_notification_delivery_leases'"
            )).scalars().all()

        assert versions == ["0009_notification_delivery_leases"]

    finally:
        engine.dispose()


def test_notification_migration_upgrades_existing_table():
    from Backend.core import schema_migrations

    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()

    try:
        with engine.begin() as connection:
            connection.execute(schema_migrations.text(
                "CREATE TABLE notifications ("
                "id INTEGER PRIMARY KEY, "
                "channel VARCHAR(30) NOT NULL, "
                "recipient VARCHAR(255) NOT NULL, "
                "subject VARCHAR(255) NOT NULL, "
                "message TEXT NOT NULL, "
                "status VARCHAR(20) NOT NULL, "
                "delivered BOOLEAN NOT NULL, "
                "retries INTEGER NOT NULL, "
                "error TEXT, "
                "created_at TIMESTAMP, "
                "updated_at TIMESTAMP, "
                "sent_at TIMESTAMP, "
                "next_retry_at TIMESTAMP)"
            ))
            connection.execute(schema_migrations.text(
                f"CREATE TABLE {schema_migrations.MIGRATION_TABLE} ("
                "version VARCHAR(80) PRIMARY KEY, "
                "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            ))
            connection.execute(schema_migrations.text(
                "INSERT INTO notifications "
                "(id, channel, recipient, subject, message, status, "
                "delivered, retries) "
                "VALUES (1, 'telegram', 'test-chat', 'Test', "
                "'Existing alert', 'PENDING', 0, 0)"
            ))

        schema_migrations.apply_versioned_migrations(engine, metadata)
        schema_migrations.apply_versioned_migrations(engine, metadata)

        columns = {
            column["name"]
            for column in inspect(engine).get_columns("notifications")
        }
        assert {"claim_token", "lease_expires_at"} <= columns

        with engine.connect() as connection:
            row = connection.execute(schema_migrations.text(
                "SELECT status, message, claim_token, lease_expires_at "
                "FROM notifications WHERE id = 1"
            )).one()

        assert row == ("PENDING", "Existing alert", None, None)

    finally:
        engine.dispose()


def test_legacy_notification_event_sql_migrations_are_removed():
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    migrations = root / "services" / "trading-service" / "database" / "migrations"

    assert not (migrations / "005_create_notification_events.sql").exists()
    assert not (migrations / "xxx_create_notification_events.sql").exists()

    schema_text = (
        root
        / "services"
        / "trading-service"
        / "Backend"
        / "core"
        / "schema_migrations.py"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS notifications (" in schema_text
    assert "0009_notification_delivery_leases" in schema_text
