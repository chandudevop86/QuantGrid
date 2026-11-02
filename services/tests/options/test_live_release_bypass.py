import sqlite3

import pytest

from Backend.application.options.live_capital_reservation import (
    ReservationRejected, reserve_live_premium, transition_live_reservation,
    release_rejected_live_reservation,
)


class FakeDhan:
    def __init__(self, filled=0):
        self.filled = filled

    def get_order_list(self):
        return {"status": "success", "data": [{
            "orderId": "order-123", "securityId": "12345",
            "orderStatus": "REJECTED", "filledQty": self.filled,
        }]}

    def get_positions(self):
        return {"status": "success", "data": [
            {"securityId": "12345", "netQty": 0},
        ]}


def test_boolean_cannot_release_capital(tmp_path):
    db = tmp_path / "risk.sqlite"
    sqlite3.connect(db).close()
    args = dict(actor_id="trader", key="request-identifier-001")
    reserve_live_premium(db, **args, premium_rupees=4900)
    transition_live_reservation(db, **args, expected_state="reserved", next_state="submitted")
    with pytest.raises(ReservationRejected, match="direct release forbidden"):
        transition_live_reservation(db, **args, expected_state="submitted", next_state="released",
                                    broker_reconciliation_confirmed=True)
    with pytest.raises(ReservationRejected, match="zero-fill"):
        release_rejected_live_reservation(db, **args, sdk_client=FakeDhan(filled=1),
                                          broker_order_id="order-123", security_id="12345")
    assert release_rejected_live_reservation(db, **args, sdk_client=FakeDhan(),
                                              broker_order_id="order-123", security_id="12345")["state"] == "released"
