import sqlite3

import pytest

from Backend.application.options.live_capital_reservation import (
    ReservationRejected, reserve_live_premium, transition_live_reservation,
)


def test_unknown_outcome_blocks_release_until_reconciled(tmp_path):
    db = tmp_path / "risk.sqlite"
    sqlite3.connect(db).close()
    args = dict(actor_id="trader", key="request-identifier-001")
    reserve_live_premium(db, **args, premium_rupees=4800)
    assert transition_live_reservation(db, **args, expected_state="reserved", next_state="submitted")["state"] == "submitted"
    transition_live_reservation(db, **args, expected_state="submitted", next_state="unknown")
    with pytest.raises(ReservationRejected, match="reconciliation"):
        transition_live_reservation(db, **args, expected_state="unknown", next_state="released")
    with pytest.raises(ReservationRejected, match="cap"):
        reserve_live_premium(db, actor_id="trader", key="another-request-001", premium_rupees=300)
    assert transition_live_reservation(db, **args, expected_state="unknown", next_state="released",
                                       broker_reconciliation_confirmed=True)["state"] == "released"
    assert reserve_live_premium(db, actor_id="trader", key="another-request-001", premium_rupees=300)["state"] == "reserved"


def test_state_transitions_reject_stale_updates(tmp_path):
    db = tmp_path / "risk.sqlite"
    sqlite3.connect(db).close()
    args = dict(actor_id="trader", key="request-identifier-001")
    reserve_live_premium(db, **args, premium_rupees=100)
    transition_live_reservation(db, **args, expected_state="reserved", next_state="submitted")
    with pytest.raises(ReservationRejected, match="state mismatch"):
        transition_live_reservation(db, **args, expected_state="reserved", next_state="unknown")
