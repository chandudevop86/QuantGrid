import sqlite3

import pytest

from Backend.application.options.paper_order_ledger import record_verified_paper_buy


def _verified():
    return {"execution_mode": "paper", "eligible": True, "symbol": "NIFTY",
            "side": "CE", "security_id": "12345", "expiry": "2026-10-29",
            "strike": 22500, "lot_size": 65, "lots": 1, "ask": 50.0}


def test_idempotent_replay_requires_intact_position_and_audit(tmp_path):
    path = tmp_path / "paper.sqlite"
    first = record_verified_paper_buy(path, "trader", "idempotency-key-001", _verified())
    assert record_verified_paper_buy(path, "trader", "idempotency-key-001", _verified())["replayed"]
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM option_paper_positions WHERE order_id=?", (first["order_id"],))
    with pytest.raises(RuntimeError, match="integrity"):
        record_verified_paper_buy(path, "trader", "idempotency-key-001", _verified())


def test_idempotent_replay_rejects_tampered_position(tmp_path):
    path = tmp_path / "paper.sqlite"
    first = record_verified_paper_buy(path, "trader", "idempotency-key-001", _verified())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE option_paper_positions SET quantity=1 WHERE order_id=?", (first["order_id"],))
    with pytest.raises(RuntimeError, match="integrity"):
        record_verified_paper_buy(path, "trader", "idempotency-key-001", _verified())
