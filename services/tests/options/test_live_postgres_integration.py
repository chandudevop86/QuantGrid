"""Opt-in real PostgreSQL concurrency tests.

Run with QUANTGRID_TEST_POSTGRES_URL pointing at an isolated disposable test DB.
Never point this suite at production: the account rows are test-owned.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from Backend.application.options.live_postgres_reservation import (
    PostgresReservationRejected, reserve_postgres_premium, bind_postgres_broker_order,
)


@pytest.fixture
def pg():
    url = os.environ.get("QUANTGRID_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set QUANTGRID_TEST_POSTGRES_URL to an isolated PostgreSQL test database")
    engine = create_engine(url, pool_size=5, max_overflow=5)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("QUANTGRID_TEST_POSTGRES_URL must be PostgreSQL")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS option_live_account_locks (
                broker_account_id TEXT PRIMARY KEY
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS option_live_pg_reservations (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                broker_account_id TEXT NOT NULL REFERENCES option_live_account_locks(broker_account_id),
                actor_id TEXT NOT NULL,
                idem_key TEXT NOT NULL,
                premium_rupees NUMERIC(14,2) NOT NULL CHECK(premium_rupees > 0),
                state TEXT NOT NULL CHECK(state IN ('reserved','submitted','unknown','filled','released')),
                UNIQUE(broker_account_id, actor_id, idem_key)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS option_live_pg_order_bindings (
                reservation_id BIGINT PRIMARY KEY REFERENCES option_live_pg_reservations(id),
                broker_account_id TEXT NOT NULL REFERENCES option_live_account_locks(broker_account_id),
                broker_order_id TEXT NOT NULL,
                security_id TEXT NOT NULL,
                UNIQUE (broker_account_id, broker_order_id)
            )
        """))
    account = "integration-" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO option_live_account_locks VALUES (:account)"), {"account": account})
    yield engine, account
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM option_live_pg_order_bindings WHERE broker_account_id=:account"),
                     {"account": account})
        conn.execute(text("DELETE FROM option_live_pg_reservations WHERE broker_account_id=:account"),
                     {"account": account})
        conn.execute(text("DELETE FROM option_live_account_locks WHERE broker_account_id=:account"),
                     {"account": account})
    engine.dispose()


def test_concurrent_reservations_never_exceed_cap(pg):
    engine, account = pg

    def reserve(i):
        try:
            return reserve_postgres_premium(
                engine, broker_account_id=account, actor_id="trader",
                key=f"parallel-request-{i:08d}", premium_rupees=1000)
        except PostgresReservationRejected:
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(reserve, range(10)))
    assert sum(result is not None for result in results) == 5
    with engine.connect() as conn:
        total = conn.execute(text("""
            SELECT COALESCE(SUM(premium_rupees),0) FROM option_live_pg_reservations
            WHERE broker_account_id=:account AND state <> 'released'
        """), {"account": account}).scalar_one()
    assert Decimal(str(total)) == Decimal("5000")


def test_idempotent_replay_and_amount_conflict(pg):
    engine, account = pg
    args = dict(broker_account_id=account, actor_id="trader",
                key="same-request-identifier-0001")
    first = reserve_postgres_premium(engine, **args, premium_rupees=1250)
    again = reserve_postgres_premium(engine, **args, premium_rupees=1250)
    assert first["reservation_id"] == again["reservation_id"]
    assert again["replayed"] is True
    with pytest.raises(PostgresReservationRejected, match="idempotency"):
        reserve_postgres_premium(engine, **args, premium_rupees=1251)


def test_account_isolation_and_unprovisioned_rejection(pg):
    engine, account = pg
    with pytest.raises(PostgresReservationRejected, match="not provisioned"):
        reserve_postgres_premium(
            engine, broker_account_id="unprovisioned-" + uuid4().hex,
            actor_id="trader", key="new-request-identifier-0001",
            premium_rupees=100)
    assert reserve_postgres_premium(
        engine, broker_account_id=account, actor_id="trader",
        key="new-request-identifier-0001", premium_rupees=100)["state"] == "reserved"


def test_immutable_order_binding_and_replay(pg):
    engine, account = pg
    args = dict(broker_account_id=account, actor_id="trader",
                key="binding-request-identifier-0001")
    reserve_postgres_premium(engine, **args, premium_rupees=250)
    first = bind_postgres_broker_order(
        engine, **args, broker_order_id="order-1", security_id="12345")
    replay = bind_postgres_broker_order(
        engine, **args, broker_order_id="order-1", security_id="12345")
    assert first["bound"] is True and first["replayed"] is False
    assert replay["replayed"] is True
    with pytest.raises(PostgresReservationRejected, match="immutable"):
        bind_postgres_broker_order(
            engine, **args, broker_order_id="order-2", security_id="12345")


def test_order_cannot_bind_to_second_reservation(pg):
    engine, account = pg
    first = dict(broker_account_id=account, actor_id="trader",
                 key="binding-request-identifier-0002")
    second = dict(broker_account_id=account, actor_id="trader",
                  key="binding-request-identifier-0003")
    for args in (first, second):
        reserve_postgres_premium(engine, **args, premium_rupees=250)
    bind_postgres_broker_order(
        engine, **first, broker_order_id="unique-order-1", security_id="12345")
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        bind_postgres_broker_order(
            engine, **second, broker_order_id="unique-order-1", security_id="12345")
