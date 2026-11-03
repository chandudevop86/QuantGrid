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
