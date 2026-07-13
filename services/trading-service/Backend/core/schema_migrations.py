from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import MetaData


POSTGRES_MIGRATION_LOCK_ID = 684_817_513_202_606_01


COMPATIBILITY_COLUMNS: dict[str, dict[str, str]] = {
    "audit_logs": {
        "actor_role": "ALTER TABLE audit_logs ADD COLUMN actor_role VARCHAR(32)",
        "status": "ALTER TABLE audit_logs ADD COLUMN status VARCHAR(40)",
        "request_id": "ALTER TABLE audit_logs ADD COLUMN request_id VARCHAR(80)",
        "reason": "ALTER TABLE audit_logs ADD COLUMN reason VARCHAR(255)",
    },
    "orders": {
        "stop_loss": "ALTER TABLE orders ADD COLUMN stop_loss FLOAT",
        "target": "ALTER TABLE orders ADD COLUMN target FLOAT",
        "trailing_stop_loss": "ALTER TABLE orders ADD COLUMN trailing_stop_loss FLOAT",
        "trailing_stop_pct": "ALTER TABLE orders ADD COLUMN trailing_stop_pct FLOAT",
        "execution_mode": "ALTER TABLE orders ADD COLUMN execution_mode VARCHAR(20) DEFAULT 'paper' NOT NULL",
        "broker_status": "ALTER TABLE orders ADD COLUMN broker_status VARCHAR(80)",
        "order_key": "ALTER TABLE orders ADD COLUMN order_key VARCHAR(160)",
    },
    "positions": {
        "exit_price": "ALTER TABLE positions ADD COLUMN exit_price FLOAT",
        "exit_reason": "ALTER TABLE positions ADD COLUMN exit_reason VARCHAR(80)",
        "trailing_stop_loss": "ALTER TABLE positions ADD COLUMN trailing_stop_loss FLOAT",
        "trailing_stop_pct": "ALTER TABLE positions ADD COLUMN trailing_stop_pct FLOAT",
        "pending_exit_correlation_id": "ALTER TABLE positions ADD COLUMN pending_exit_correlation_id VARCHAR(120)",
        "pending_exit_broker_order_id": "ALTER TABLE positions ADD COLUMN pending_exit_broker_order_id VARCHAR(120)",
    },
    "paper_trades": {
        "broker_status": "ALTER TABLE paper_trades ADD COLUMN broker_status VARCHAR(80)",
        "raw_safe_broker_response": "ALTER TABLE paper_trades ADD COLUMN raw_safe_broker_response TEXT",
        "trailing_stop_loss": "ALTER TABLE paper_trades ADD COLUMN trailing_stop_loss FLOAT",
        "trailing_stop_pct": "ALTER TABLE paper_trades ADD COLUMN trailing_stop_pct FLOAT",
    },
    "trade_journal": {
        "status": "ALTER TABLE trade_journal ADD COLUMN status VARCHAR(40) NOT NULL DEFAULT 'recorded'",
        "quantity": "ALTER TABLE trade_journal ADD COLUMN quantity INTEGER",
        "reason": "ALTER TABLE trade_journal ADD COLUMN reason TEXT",
        "source": "ALTER TABLE trade_journal ADD COLUMN source VARCHAR(40) NOT NULL DEFAULT 'manual'",
    },
}

MIGRATION_TABLE = "quantgrid_schema_migrations"
BASELINE_VERSION = "0001_metadata_baseline"
COMPATIBILITY_VERSION = "0002_legacy_columns"


def apply_versioned_migrations(engine: Engine, metadata: MetaData) -> None:
    """Own schema initialization and legacy upgrades behind a durable version ledger."""

    # Existing deployments predate a migration framework. Treat their SQLAlchemy
    # schema as the explicit baseline, then version every subsequent upgrade.
    metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} ("
            "version VARCHAR(80) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)"
        ))
        applied = {row[0] for row in connection.execute(text(f"SELECT version FROM {MIGRATION_TABLE}"))}
        if BASELINE_VERSION not in applied:
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),
                {"version": BASELINE_VERSION},
            )

    if COMPATIBILITY_VERSION not in applied:
        apply_compatibility_migrations(engine, COMPATIBILITY_COLUMNS)
        with engine.begin() as connection:
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),
                {"version": COMPATIBILITY_VERSION},
            )


def apply_compatibility_migrations(engine: Engine, tables: Iterable[str]) -> None:
    """Apply the small, idempotent upgrades that predate versioned migrations."""
    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": POSTGRES_MIGRATION_LOCK_ID},
            )

        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        pending: list[str] = []
        for table in tables:
            additions = COMPATIBILITY_COLUMNS.get(table)
            if additions is None:
                raise ValueError(f"Unknown compatibility migration table: {table}")
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            pending.extend(
                _statement_for_dialect(statement, dialect)
                for column, statement in additions.items()
                if column not in existing_columns
            )

        for statement in pending:
            connection.execute(text(statement))


def _statement_for_dialect(statement: str, dialect: str) -> str:
    if dialect == "postgresql":
        return statement.replace(" ADD COLUMN ", " ADD COLUMN IF NOT EXISTS ", 1)
    return statement
