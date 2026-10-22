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
        "execution_mode": "ALTER TABLE positions ADD COLUMN execution_mode VARCHAR(20) DEFAULT 'paper' NOT NULL",
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
        "gross_pnl": "ALTER TABLE trade_journal ADD COLUMN gross_pnl FLOAT",
        "total_costs": "ALTER TABLE trade_journal ADD COLUMN total_costs FLOAT",
        "net_pnl": "ALTER TABLE trade_journal ADD COLUMN net_pnl FLOAT",
        "broker_order_id": "ALTER TABLE trade_journal ADD COLUMN broker_order_id VARCHAR(120)",
    },
}

MIGRATION_TABLE = "quantgrid_schema_migrations"
BASELINE_VERSION = "0001_metadata_baseline"
COMPATIBILITY_VERSION = "0002_legacy_columns"
SUBSCRIPTION_ENTITLEMENTS_VERSION = "0003_subscription_entitlements"
INSTITUTIONAL_METRICS_VERSION = "0004_institutional_metrics"
PAPER_TRADE_COST_EVIDENCE_VERSION = "0005_paper_trade_cost_evidence"
PAPER_TRADE_IDEMPOTENCY_VERSION = "0006_paper_trade_idempotency"
BROKER_SUBMISSION_INTENTS_VERSION = "0007_broker_submission_intents"
POSITION_EXECUTION_MODE_VERSION = "0008_position_execution_mode"
NOTIFICATION_DELIVERY_LEASES_VERSION = "0009_notification_delivery_leases"
NOTIFICATION_DEDUPLICATION_VERSION = "0010_notification_deduplication"
PROTECTION_ALERT_EPISODES_VERSION = "0011_protection_alert_episodes"
SIGNAL_EVALUATION_EVENTS_VERSION = "0012_signal_evaluation_events"

def apply_versioned_migrations(engine: Engine, metadata: MetaData) -> None:
    """Own schema initialization and legacy upgrades behind a durable version ledger."""

    # Existing deployments predate a migration framework. Bootstrap that legacy
    # baseline exactly once; after the ledger exists, startup must not create new
    # model tables implicitly. Future schema changes belong in explicit versions.
    baseline_required = MIGRATION_TABLE not in set(inspect(engine).get_table_names())
    if baseline_required:
        metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} ("  # nosec B608
            "version VARCHAR(80) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)"
        ))
        applied = {row[0] for row in connection.execute(text(f"SELECT version FROM {MIGRATION_TABLE}"))}  # nosec B608
        if BASELINE_VERSION not in applied:
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),  # nosec B608
                {"version": BASELINE_VERSION},
            )

    if COMPATIBILITY_VERSION not in applied:
        apply_compatibility_migrations(engine, COMPATIBILITY_COLUMNS)
        with engine.begin() as connection:
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),  # nosec B608
                {"version": COMPATIBILITY_VERSION},
            )

    with engine.begin() as connection:
        applied = {row[0] for row in connection.execute(text(f"SELECT version FROM {MIGRATION_TABLE}"))}  # nosec B608
        if SUBSCRIPTION_ENTITLEMENTS_VERSION not in applied:
            primary_key = "SERIAL PRIMARY KEY" if engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY"
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS user_entitlement_overrides ("
                f"id {primary_key}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "entitlement_key VARCHAR(120) NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, limit_value INTEGER, "
                "reason VARCHAR(255) NOT NULL, expires_at TIMESTAMP, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            ))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_entitlement_overrides_user_id ON user_entitlement_overrides (user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_entitlement_overrides_key ON user_entitlement_overrides (entitlement_key)"))
            connection.execute(  # nosec B608
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),  # nosec B608
                {"version": SUBSCRIPTION_ENTITLEMENTS_VERSION},
            )

    with engine.begin() as connection:
        applied = {row[0] for row in connection.execute(
            text(f"SELECT version FROM {MIGRATION_TABLE}")
        )}

        if INSTITUTIONAL_METRICS_VERSION not in applied:
            connection.execute(text(
                """
                CREATE TABLE IF NOT EXISTS institutional_metrics (
                    id SERIAL PRIMARY KEY,
                    fii_cash FLOAT,
                    dii_cash FLOAT,
                    fii_index_future FLOAT,
                    gift_nifty FLOAT,
                    india_vix FLOAT,
                    usdinr FLOAT,
                    crude_oil FLOAT,
                    gold FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            ))

            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),
                {"version": INSTITUTIONAL_METRICS_VERSION},
            )

    with engine.begin() as connection:
        applied = {row[0] for row in connection.execute(
            text(f"SELECT version FROM {MIGRATION_TABLE}")
        )}

    if PAPER_TRADE_COST_EVIDENCE_VERSION not in applied:
        apply_compatibility_migrations(engine, ["trade_journal"])
        with engine.begin() as connection:
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),  # nosec B608
                {"version": PAPER_TRADE_COST_EVIDENCE_VERSION},
            )


    with engine.begin() as connection:
        applied = {row[0] for row in connection.execute(
            text(f"SELECT version FROM {MIGRATION_TABLE}")
        )}

        if PAPER_TRADE_IDEMPOTENCY_VERSION not in applied:
            existing_tables = set(inspect(connection).get_table_names())
            if "paper_trades" in existing_tables:
                connection.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_trades_signal_identity "
                    "ON paper_trades (strategy, symbol, signal_time)"
                ))
                connection.execute(
                    text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),  # nosec B608
                    {"version": PAPER_TRADE_IDEMPOTENCY_VERSION},
                )


    # Persistent broker submission claims are created explicitly for existing
    # installations, not only during metadata baseline creation.
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"),
                               {"lock_id": POSTGRES_MIGRATION_LOCK_ID})
        applied = {row[0] for row in connection.execute(
            text(f"SELECT version FROM {MIGRATION_TABLE}")
        )}
        if BROKER_SUBMISSION_INTENTS_VERSION not in applied:
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS broker_submission_intents ("
                "local_order_id VARCHAR(120) PRIMARY KEY, "
                "logical_key VARCHAR(160) NOT NULL, "
                "correlation_id VARCHAR(120) NOT NULL UNIQUE, "
                "broker_order_id VARCHAR(120), "
                "status VARCHAR(40) NOT NULL, "
                "created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_submission_intents_active_key "
                "ON broker_submission_intents (logical_key) "
                "WHERE status IN ('claimed', 'reconciliation_required', 'submitted', "
                "'open', 'partially_filled')"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_submission_intents_broker_id "
                "ON broker_submission_intents (broker_order_id)"
            ))
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),
                {"version": BROKER_SUBMISSION_INTENTS_VERSION},
            )



    # Positions must carry the same execution-mode ownership as their source
    # orders so broker reconciliation can never cross PAPER/LIVE boundaries.
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"),
                               {"lock_id": POSTGRES_MIGRATION_LOCK_ID})
        applied = {row[0] for row in connection.execute(
            text(f"SELECT version FROM {MIGRATION_TABLE}")
        )}
    if POSITION_EXECUTION_MODE_VERSION not in applied:
        apply_compatibility_migrations(engine, ["positions"])
        with engine.begin() as connection:
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),  # nosec B608
                {"version": POSITION_EXECUTION_MODE_VERSION},
            )



    apply_notification_delivery_leases_migration(engine)
    apply_notification_deduplication_migration(engine)
    apply_protection_alert_episodes_migration(engine)
    apply_signal_evaluation_events_migration(engine)

def apply_notification_delivery_leases_migration(engine: Engine) -> None:
    """Create or upgrade persistent notification delivery storage."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": POSTGRES_MIGRATION_LOCK_ID},
            )

        applied = {
            row[0]
            for row in connection.execute(
                text(f"SELECT version FROM {MIGRATION_TABLE}")
            )
        }
        if NOTIFICATION_DELIVERY_LEASES_VERSION in applied:
            return

        dialect = engine.dialect.name
        primary_key = (
            "SERIAL PRIMARY KEY"
            if dialect == "postgresql"
            else "INTEGER PRIMARY KEY"
        )

        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS notifications ("
            f"id {primary_key}, "
            "channel VARCHAR(30) NOT NULL, "
            "recipient VARCHAR(255) NOT NULL, "
            "subject VARCHAR(255) NOT NULL, "
            "message TEXT NOT NULL, "
            "status VARCHAR(20) NOT NULL DEFAULT 'PENDING', "
            "delivered BOOLEAN NOT NULL DEFAULT FALSE, "
            "retries INTEGER NOT NULL DEFAULT 0, "
            "error TEXT, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "sent_at TIMESTAMP, "
            "claim_token VARCHAR(80), "
            "lease_expires_at TIMESTAMP, "
            "next_retry_at TIMESTAMP)"
        ))

        existing_columns = {
            column["name"]
            for column in inspect(connection).get_columns("notifications")
        }

        for column, definition in (
            ("claim_token", "VARCHAR(80)"),
            ("lease_expires_at", "TIMESTAMP"),
        ):
            if column not in existing_columns:
                clause = (
                    "ADD COLUMN IF NOT EXISTS"
                    if dialect == "postgresql"
                    else "ADD COLUMN"
                )
                connection.execute(text(
                    f"ALTER TABLE notifications {clause} "
                    f"{column} {definition}"
                ))

        for name, column in (
            ("ix_notifications_id", "id"),
            ("ix_notifications_channel", "channel"),
            ("ix_notifications_status", "status"),
            ("ix_notifications_next_retry_at", "next_retry_at"),
            ("ix_notifications_lease_expires_at", "lease_expires_at"),
        ):
            connection.execute(text(
                f"CREATE INDEX IF NOT EXISTS {name} "
                f"ON notifications ({column})"
            ))

        connection.execute(
            text(
                f"INSERT INTO {MIGRATION_TABLE} (version) "
                "VALUES (:version)"
            ),
            {"version": NOTIFICATION_DELIVERY_LEASES_VERSION},
        )

def apply_notification_deduplication_migration(engine: Engine) -> None:
    """Add database-enforced notification deduplication."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": POSTGRES_MIGRATION_LOCK_ID},
            )

        applied = {
            row[0]
            for row in connection.execute(
                text(f"SELECT version FROM {MIGRATION_TABLE}")
            )
        }
        if NOTIFICATION_DEDUPLICATION_VERSION in applied:
            return

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("notifications")
        }

        if "dedup_key" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE notifications "
                    "ADD COLUMN dedup_key VARCHAR(160)"
                )
            )

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_notifications_dedup_key "
                "ON notifications (dedup_key)"
            )
        )

        connection.execute(
            text(
                f"INSERT INTO {MIGRATION_TABLE} (version) "
                "VALUES (:version)"
            ),
            {"version": NOTIFICATION_DEDUPLICATION_VERSION},
        )


def apply_protection_alert_episodes_migration(
    engine: Engine,
) -> None:
    """Create durable protection-failure episode storage."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": POSTGRES_MIGRATION_LOCK_ID},
            )

        applied = {
            row[0]
            for row in connection.execute(
                text(f"SELECT version FROM {MIGRATION_TABLE}")
            )
        }

        if PROTECTION_ALERT_EPISODES_VERSION in applied:
            return

        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS protection_alert_episodes ("
            "episode_id VARCHAR(36) PRIMARY KEY, "
            "local_order_id VARCHAR(120) NOT NULL, "
            "opened_at TIMESTAMP NOT NULL, "
            "closed_at TIMESTAMP NULL"
            ")"
        ))

        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_protection_alert_active_order "
            "ON protection_alert_episodes (local_order_id) "
            "WHERE closed_at IS NULL"
        ))

        connection.execute(
            text(
                f"INSERT INTO {MIGRATION_TABLE} (version) "
                "VALUES (:version)"
            ),
            {"version": PROTECTION_ALERT_EPISODES_VERSION},
        )



def apply_signal_evaluation_events_migration(engine: Engine) -> None:
    """Create an append-only, uniquely keyed audit event table for existing installs."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": POSTGRES_MIGRATION_LOCK_ID},
            )
        applied = {row[0] for row in connection.execute(text(f"SELECT version FROM {MIGRATION_TABLE}"))}
        if SIGNAL_EVALUATION_EVENTS_VERSION in applied:
            return
        pk = "BIGSERIAL PRIMARY KEY" if engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS signal_evaluation_events ("
            f"id {pk}, evaluation_id VARCHAR(64) NOT NULL, "
            "event_type VARCHAR(40) NOT NULL, signal_id VARCHAR(64) NOT NULL, "
            "strategy VARCHAR(80) NOT NULL, symbol VARCHAR(32) NOT NULL, "
            "side VARCHAR(20) NOT NULL, signal_time VARCHAR(64) NOT NULL, "
            "snapshot_time VARCHAR(64) NOT NULL, status VARCHAR(40) NOT NULL, "
            "reason VARCHAR(80) NOT NULL, mtf_bias VARCHAR(40) NOT NULL, "
            "evidence_json TEXT NOT NULL, evaluated_at TIMESTAMP NOT NULL, "
            "CONSTRAINT uq_signal_eval_event UNIQUE (evaluation_id, event_type))"
        ))
        connection.execute(text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),
                           {"version": SIGNAL_EVALUATION_EVENTS_VERSION})


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
