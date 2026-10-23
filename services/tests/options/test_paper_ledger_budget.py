import sqlite3

import pytest

from Backend.application.options.paper_order_ledger import record_verified_paper_buy


def _verified():
    return dict(execution_mode="paper", eligible=True, symbol="NIFTY",
                side="CE", security_id="12345", expiry="2026-10-29",
                strike=22500, lot_size=65, lots=1, ask=50.0)


def test_paper_cap_is_aggregate_and_idempotent(tmp_path):
    path = tmp_path / "ledger.sqlite"
    first = record_verified_paper_buy(path, "actor", "request-key-000001", _verified(),
                                      max_open_premium_rupees=5000)
    assert record_verified_paper_buy(path, "actor", "request-key-000001", _verified(),
                                    max_open_premium_rupees=5000)["replayed"]
    with pytest.raises(ValueError, match="exposure limit"):
        record_verified_paper_buy(path, "actor", "request-key-000002", _verified(),
                                  max_open_premium_rupees=5000)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM option_paper_orders").fetchone()[0] == 1
    assert first["broker_submitted"] is False


def test_paper_cap_is_actor_scoped(tmp_path):
    path = tmp_path / "ledger.sqlite"
    record_verified_paper_buy(path, "actor-a", "request-key-000001", _verified(),
                              max_open_premium_rupees=4000)
    record_verified_paper_buy(path, "actor-b", "request-key-000001", _verified(),
                              max_open_premium_rupees=4000)


@pytest.mark.parametrize("limit", [None, True, -1, float("nan"), float("inf")])
def test_invalid_paper_limit_rejected(tmp_path, limit):
    with pytest.raises(ValueError, match="limit"):
        record_verified_paper_buy(tmp_path / "ledger.sqlite", "actor",
                                  "request-key-000001", _verified(),
                                  max_open_premium_rupees=limit)
