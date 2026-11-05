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


def test_concurrent_reservations_cannot_exceed_cap(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db_path = tmp_path / "concurrent-risk.sqlite"
    sqlite3.connect(db_path).close()

    barrier = Barrier(2)

    def attempt(actor, key, amount):
        barrier.wait(timeout=10)
        try:
            result = reserve_live_premium(
                db_path,
                actor_id=actor,
                key=key,
                premium_rupees=amount,
                cap_rupees=5000,
            )
            return ("accepted", result)
        except ReservationRejected as exc:
            return ("rejected", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                attempt, "actor-a",
                "concurrent-key-aaaa", 3200
            ),
            pool.submit(
                attempt, "actor-b",
                "concurrent-key-bbbb", 1900
            ),
        ]
        results = [future.result(timeout=40) for future in futures]

    assert sum(r[0] == "accepted" for r in results) == 1
    assert sum(r[0] == "rejected" for r in results) == 1
    assert any(
        "cap" in r[1]
        for r in results
        if r[0] == "rejected"
    )

    with sqlite3.connect(db_path) as db:
        total = db.execute(
            "SELECT COALESCE(SUM(premium_rupees), 0) "
            "FROM option_live_reservations "
            "WHERE state != 'released'"
        ).fetchone()[0]

        count = db.execute(
            "SELECT COUNT(*) FROM option_live_reservations"
        ).fetchone()[0]

    assert total <= 5000
    assert count == 1
