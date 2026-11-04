from types import SimpleNamespace

import pytest

from Backend.application.options.live_postgres_reservation import (
    PostgresReservationRejected, _amount, reserve_postgres_premium,
)


@pytest.mark.parametrize("value", [0, -1, True, "NaN", "Infinity", "1.001", None])
def test_invalid_amount_fails_closed(value):
    with pytest.raises(PostgresReservationRejected):
        _amount(value)


def test_non_postgres_engine_rejected_before_database_access():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    with pytest.raises(PostgresReservationRejected, match="PostgreSQL required"):
        reserve_postgres_premium(
            engine, broker_account_id="broker-1", actor_id="trader",
            key="request-identifier-001", premium_rupees=100,
        )


def test_cap_above_5000_rejected():
    class Engine:
        dialect = SimpleNamespace(name="postgresql")
        def begin(self):
            raise AssertionError("no database connection expected")
    with pytest.raises(PostgresReservationRejected, match="cap"):
        reserve_postgres_premium(
            Engine(), broker_account_id="broker-1", actor_id="trader",
            key="request-identifier-001", premium_rupees=100, cap_rupees=5001,
        )


def test_release_and_binding_reject_sqlite():
    from Backend.application.options.live_postgres_reservation import (
        bind_postgres_broker_order, release_postgres_rejected_order,
    )
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    args = dict(broker_account_id="account-1", actor_id="trader",
                key="request-identifier-001", broker_order_id="order-1",
                security_id="12345")
    with pytest.raises(PostgresReservationRejected, match="PostgreSQL"):
        bind_postgres_broker_order(engine, **args)
    with pytest.raises(PostgresReservationRejected, match="PostgreSQL"):
        release_postgres_rejected_order(engine, **args, sdk_client=None)

def test_submission_transition_rejects_sqlite():
    from Backend.application.options.live_postgres_reservation import transition_postgres_reservation
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    with pytest.raises(PostgresReservationRejected, match="PostgreSQL"):
        transition_postgres_reservation(
            engine, broker_account_id="acct-1", actor_id="trader",
            key="request-identifier-001", expected_state="reserved",
            next_state="unknown",
        )


@pytest.mark.parametrize("expected,next_state", [
    ("reserved", "submitted"),
    ("unknown", "released"),
    ("submitted", "unknown"),
    ("unknown", "reserved"),
    ("reserved", "released"),
])
def test_submission_transition_forbids_unsafe_state_changes(expected, next_state):
    from Backend.application.options.live_postgres_reservation import transition_postgres_reservation

    class Engine:
        dialect = SimpleNamespace(name="postgresql")
        def begin(self):
            raise AssertionError("invalid transitions must not access database")

    with pytest.raises(PostgresReservationRejected, match="forbidden"):
        transition_postgres_reservation(
            Engine(), broker_account_id="acct-1", actor_id="trader",
            key="request-identifier-001", expected_state=expected,
            next_state=next_state,
        )
