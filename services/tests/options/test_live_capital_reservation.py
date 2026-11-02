import sqlite3

import pytest

from Backend.application.options.live_capital_reservation import reserve_live_premium, ReservationRejected


def test_cap_and_idempotency(tmp_path):
    db = tmp_path / "risk.sqlite"
    sqlite3.connect(db).close()
    first = reserve_live_premium(db, actor_id="a", key="first-request-key", premium_rupees=3200)
    assert first["state"] == "reserved"
    assert reserve_live_premium(db, actor_id="a", key="first-request-key", premium_rupees=3200)["replayed"]
    with pytest.raises(ReservationRejected, match="cap"):
        reserve_live_premium(db, actor_id="b", key="second-request-key", premium_rupees=1900)
    with pytest.raises(ReservationRejected, match="conflict"):
        reserve_live_premium(db, actor_id="a", key="first-request-key", premium_rupees=3100)


def test_missing_storage_and_invalid_amount_fail_closed(tmp_path):
    with pytest.raises(ReservationRejected, match="not provisioned"):
        reserve_live_premium(tmp_path / "missing.sqlite", actor_id="a", key="first-request-key", premium_rupees=100)
    db = tmp_path / "risk.sqlite"
    sqlite3.connect(db).close()
    for amount in (float("nan"), float("inf"), True, -1, 0):
        with pytest.raises(ReservationRejected):
            reserve_live_premium(db, actor_id="a", key="first-request-key", premium_rupees=amount)
