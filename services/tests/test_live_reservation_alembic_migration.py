"""Tests for PostgreSQL live-reservation migration (no live broker actions)."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic/versions/0009_option_live_reservations.py"


def _module():
    # CI does not install Alembic; exercise migration operations with a mocked
    # op facade while retaining the production import in the migration file.
    import types
    source = MIGRATION.read_text(encoding="utf-8")
    source = source.replace("from alembic import op", "op = None", 1)
    module = types.ModuleType("live_reservation_migration_0009")
    exec(compile(source, str(MIGRATION), "exec"), module.__dict__)
    return module


def test_migration_requires_postgresql(monkeypatch):
    migration = _module()
    fake = MagicMock()
    fake.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    monkeypatch.setattr(migration, "op", fake)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        migration.upgrade()
    fake.create_table.assert_not_called()


def test_migration_creates_all_reservation_tables(monkeypatch):
    migration = _module()
    fake = MagicMock()
    fake.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(migration, "op", fake)
    migration.upgrade()
    names = [call.args[0] for call in fake.create_table.call_args_list]
    assert names == [
        "option_live_account_locks",
        "option_live_pg_reservations",
        "option_live_pg_order_bindings",
    ]
    fake.create_index.assert_called_once()


def test_migration_refuses_destructive_downgrade():
    with pytest.raises(RuntimeError, match="cannot be dropped"):
        _module().downgrade()
