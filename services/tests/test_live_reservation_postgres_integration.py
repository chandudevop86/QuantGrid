"""Run migration operations against real, isolated PostgreSQL without broker calls."""
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "alembic/versions/0009_option_live_reservations.py"


def test_real_postgres_reservation_migration():
    url = os.environ.get("QUANTGRID_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("isolated PostgreSQL URL required")
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = sa.create_engine(url)
    assert engine.dialect.name == "postgresql"
    spec = importlib.util.spec_from_file_location("reservation_revision_0009", REVISION)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        original_op = revision.op
        revision.op = operations
        try:
            revision.upgrade()
        finally:
            revision.op = original_op
        inspector = sa.inspect(conn)
        assert set(("option_live_account_locks", "option_live_pg_reservations", "option_live_pg_order_bindings")).issubset(inspector.get_table_names())
        conn.execute(sa.text("INSERT INTO option_live_account_locks (broker_account_id) VALUES ('ci-only')"))
        conn.execute(sa.text("""INSERT INTO option_live_pg_reservations
          (broker_account_id, actor_id, idem_key, premium_rupees, state)
          VALUES ('ci-only','actor','key',5000,'reserved')"""))
        with conn.begin_nested():
            # A duplicate idempotency key must fail at the database level.
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text("""INSERT INTO option_live_pg_reservations
                  (broker_account_id, actor_id, idem_key, premium_rupees, state)
                  VALUES ('ci-only','actor','key',100,'reserved')"""))
        with conn.begin_nested():
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text("""INSERT INTO option_live_pg_reservations
                  (broker_account_id, actor_id, idem_key, premium_rupees, state)
                  VALUES ('ci-only','actor','bad',-1,'reserved')"""))
    engine.dispose()
