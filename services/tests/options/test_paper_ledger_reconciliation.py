import sqlite3
import pytest
from Backend.application.options.paper_order_ledger import record_verified_paper_buy
from Backend.application.options.paper_ledger_reconciliation import (
    reconcile_paper_ledger, PaperLedgerMismatch,
)


def _verified():
    return dict(execution_mode="paper", eligible=True, symbol="NIFTY",
                side="CE", security_id="12345", expiry="2026-10-29",
                strike=22500, lot_size=65, lots=1, ask=50.0)


def test_order_to_position_and_audit_reconciliation(tmp_path):
    db = tmp_path / "paper.sqlite"
    result = record_verified_paper_buy(db, "user-1", "request-key-000001", _verified())
    assert result["broker_submitted"] is False
    record_verified_paper_buy(db, "user-1", "request-key-000001", _verified())
    assert reconcile_paper_ledger(db)["orders"] == 1


def test_missing_position_fails_reconciliation(tmp_path):
    db = tmp_path / "paper.sqlite"
    result = record_verified_paper_buy(db, "user-1", "request-key-000001", _verified())
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM option_paper_positions WHERE order_id=?", (result["order_id"],))
    with pytest.raises(PaperLedgerMismatch):
        reconcile_paper_ledger(db)


def test_orphan_audit_fails_reconciliation(tmp_path):
    db = tmp_path / "paper.sqlite"
    record_verified_paper_buy(db, "user-1", "request-key-000001", _verified())
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO option_paper_audit(order_id,actor_id,event,created_at) VALUES(999,'u','fake','now')")
    with pytest.raises(PaperLedgerMismatch):
        reconcile_paper_ledger(db)
