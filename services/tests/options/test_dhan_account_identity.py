import pytest

from Backend.application.options.dhan_account_identity import (
    DhanIdentityUnavailable, verify_dhan_account_identity,
)


class Client:
    def __init__(self, payload):
        self.payload = payload

    def get_fund_limits(self):
        return self.payload


@pytest.mark.parametrize("payload", [
    None, {}, {"status": "failure", "data": {"dhanClientId": "123"}},
    {"status": "success", "data": {}},
    {"status": "success", "data": {"dhanClientId": "other"}},
    {"status": "success", "data": []},
])
def test_unverified_account_fails_closed(payload):
    with pytest.raises(DhanIdentityUnavailable):
        verify_dhan_account_identity(
            sdk_client=Client(payload), configured_client_id="123",
        )


def test_matching_explicit_broker_identity():
    client = Client({"status": "success", "data": {"dhanClientId": "123"}})
    assert verify_dhan_account_identity(
        sdk_client=client, configured_client_id="123") == "123"


def test_missing_server_config_fails_closed():
    with pytest.raises(DhanIdentityUnavailable):
        verify_dhan_account_identity(
            sdk_client=Client({"status": "success", "data": {"dhanClientId": "123"}}),
            configured_client_id="",
        )


def test_postgres_release_rejects_missing_identity_before_database_access():
    from types import SimpleNamespace
    from Backend.application.options.live_postgres_reservation import (
        release_postgres_rejected_order,
    )

    class Engine:
        dialect = SimpleNamespace(name="postgresql")

        def begin(self):
            raise AssertionError("database must not be accessed")

    with pytest.raises(DhanIdentityUnavailable):
        release_postgres_rejected_order(
            Engine(), broker_account_id="123", actor_id="trader",
            key="request-identifier-0001", broker_order_id="order-1",
            security_id="12345", sdk_client=Client({
                "status": "success", "data": {"dhanClientId": "123"}
            }),
        )


def test_postgres_release_rejects_other_authenticated_account():
    from types import SimpleNamespace
    from Backend.application.options.live_postgres_reservation import (
        PostgresReservationRejected, release_postgres_rejected_order,
    )

    class Engine:
        dialect = SimpleNamespace(name="postgresql")

        def begin(self):
            raise AssertionError("database must not be accessed")

    with pytest.raises(PostgresReservationRejected, match="account mismatch"):
        release_postgres_rejected_order(
            Engine(), broker_account_id="123", actor_id="trader",
            key="request-identifier-0001", broker_order_id="order-1",
            security_id="12345", configured_client_id="456",
            sdk_client=Client({
                "status": "success", "data": {"dhanClientId": "456"}
            }),
        )
