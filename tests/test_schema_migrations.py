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
    assert versions == [schema_migrations.BASELINE_VERSION, schema_migrations.COMPATIBILITY_VERSION]
    assert "execution_mode" in {column["name"] for column in inspect(engine).get_columns("orders")}
