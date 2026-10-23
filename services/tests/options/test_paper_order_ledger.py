import sqlite3
import pytest
from Backend.application.options.paper_order_ledger import (
    record_verified_paper_buy, IdempotencyConflict,
)


def verified():
    return dict(execution_mode="paper", eligible=True, symbol="NIFTY", side="CE",
                security_id="12345", expiry="2026-10-29", strike=22500,
                lot_size=65, lots=1, ask=101.5)


def test_atomic_idempotent_paper_order(tmp_path):
    db = tmp_path / "paper.sqlite"
    first = record_verified_paper_buy(db, "trader-1", "request-key-000001", verified())
    again = record_verified_paper_buy(db, "trader-1", "request-key-000001", verified())
    assert first["order_id"] == again["order_id"]
    assert not first["replayed"] and again["replayed"]
    assert not first["broker_submitted"]
    with sqlite3.connect(db) as conn:
        for table in ("option_paper_orders", "option_paper_positions", "option_paper_audit"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


def test_conflicting_reuse_rejected(tmp_path):
    db = tmp_path / "paper.sqlite"
    record_verified_paper_buy(db, "trader-1", "request-key-000001", verified())
    with pytest.raises(IdempotencyConflict):
        record_verified_paper_buy(db, "trader-1", "request-key-000001",
                                  {**verified(), "lots": 2})


def test_live_orders_cannot_be_persisted(tmp_path):
    with pytest.raises(ValueError):
        record_verified_paper_buy(tmp_path / "paper.sqlite", "trader-1",
                                  "request-key-000001",
                                  {**verified(), "execution_mode": "live"})


def test_invalid_price_and_identity_rejected(tmp_path):
    with pytest.raises(ValueError):
        record_verified_paper_buy(tmp_path / "paper.sqlite", "trader-1",
                                  "request-key-000001",
                                  {**verified(), "ask": float("nan")})
