from datetime import datetime, timezone

from Backend.application.options.live_broker_reconciliation import can_release_live_reservation


def test_rejected_zero_fill_with_no_position_can_release():
    now = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    args = dict(expected_order_id="ord123", expected_security_id="12345",
                broker_order={"order_id": "ord123", "security_id": "12345",
                              "status": "REJECTED", "filled_quantity": 0},
                broker_positions=[{"security_id": "12345", "net_quantity": 0}],
                fetched_at=now.isoformat(), now=now)
    assert can_release_live_reservation(**args)
    assert not can_release_live_reservation(**{**args, "broker_order": {**args["broker_order"], "filled_quantity": 1}})
    assert not can_release_live_reservation(**{**args, "broker_positions": [{"security_id": "12345", "net_quantity": 1}]})
    assert not can_release_live_reservation(**{**args, "broker_order": {**args["broker_order"], "status": "FILLED"}})
    assert not can_release_live_reservation(**{**args, "broker_order": {**args["broker_order"], "order_id": "other"}})
    assert not can_release_live_reservation(**{**args, "fetched_at": "2026-11-02T08:00:00Z"})
    assert not can_release_live_reservation(**{**args, "broker_positions": [{"security_id": "12345"}]})


def test_unknown_order_does_not_release():
    now = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    assert not can_release_live_reservation(expected_order_id="ord123", expected_security_id="12345",
        broker_order={"order_id": "ord123", "security_id": "12345", "status": "UNKNOWN", "filled_quantity": 0},
        broker_positions=[], fetched_at=now.isoformat(), now=now)
