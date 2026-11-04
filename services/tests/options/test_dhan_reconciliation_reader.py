import pytest

from Backend.application.options.dhan_reconciliation_reader import (
    BrokerReconciliationUnavailable, verify_dhan_nonfill,
)


class FakeDhan:
    def __init__(self, status="REJECTED", filled=0, net=0):
        self.status, self.filled, self.net = status, filled, net

    def get_order_list(self):
        return {"status": "success", "data": [{
            "orderId": "order-123", "securityId": "12345",
            "orderStatus": self.status, "filledQty": self.filled,
        }]}

    def get_positions(self):
        return {"status": "success", "data": [{
            "securityId": "12345", "netQty": self.net,
        }]}


def test_terminal_zero_fill_and_zero_position():
    assert verify_dhan_nonfill(sdk_client=FakeDhan(), order_id="order-123",
                               security_id="12345")["release_eligible"]


@pytest.mark.parametrize("status,filled,net", [
    ("TRADED", 1, 0), ("CANCELLED", 1, 0), ("REJECTED", 0, 1),
    ("PENDING", 0, 0),
])
def test_unsafe_broker_states_block_release(status, filled, net):
    result = verify_dhan_nonfill(sdk_client=FakeDhan(status, filled, net),
                                 order_id="order-123", security_id="12345")
    assert not result["release_eligible"]


def test_unverified_order_blocks():
    with pytest.raises(BrokerReconciliationUnavailable):
        verify_dhan_nonfill(sdk_client=FakeDhan(), order_id="wrong", security_id="12345")
