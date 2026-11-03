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
