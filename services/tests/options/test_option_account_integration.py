import pytest


def seed_option(tmp_path, monkeypatch):
    from Backend.application.options import paper_order_ledger as ledger

    path = tmp_path / "options.sqlite3"
    monkeypatch.setenv("QUANTGRID_OPTION_PAPER_LEDGER", str(path))
    result = ledger.record_verified_paper_buy(path, "user:1", "account-integration-option", {
        "execution_mode": "paper", "eligible": True, "symbol": "NIFTY", "side": "CE",
        "security_id": "12345", "expiry": "2099-12-31", "strike": 25000,
        "lot_size": 65, "lots": 1, "ask": 50.0,
    })
    return path, result["order_id"]


def test_option_risk_journal_and_net_pnl_count_once(app_client, admin_headers, tmp_path, monkeypatch):
    from Backend.application import paper_trade_store as store
    from Backend.application.options import paper_order_ledger as ledger

    path, order_id = seed_option(tmp_path, monkeypatch)
    assert store.risk_status()["open_positions"] == 1
    assert store.risk_status(include_options=False)["open_positions"] == 0
    assert store.risk_status()["current_exposure"] == 3250
    closed = ledger.close_option_position(path, order_id, 70, "target_hit")
    assert closed["gross_pnl"] == 1300
    assert closed["net_pnl"] == round(1300 - closed["total_costs"], 2)
    assert closed["net_pnl"] < 1300
    risk = store.risk_status()
    assert risk["open_positions"] == 0
    assert risk["daily_pnl"] == closed["net_pnl"]
    assert risk["realized_pnl"] == closed["net_pnl"]
    assert risk["trades_today"] == 1
    assert store.risk_status(include_options=False)["daily_pnl"] == 0
    rows = store.list_paper_trades()
    assert len(rows) == 1 and rows[0]["id"] == -order_id
    journal = app_client.get("/api/trades/journal", headers=admin_headers)
    assert journal.status_code == 200
    assert journal.json()["rows"][0]["id"] == -order_id
    assert journal.json()["summary"]["pnl"] == closed["net_pnl"]
    assert store.list_paper_trades(include_options=False) == []
    with pytest.raises(ValueError, match="read-only"):
        store.update_trade_journal_entry(-order_id, {"pnl": 999999})
    changed = app_client.patch(f"/api/trades/journal/{-order_id}", headers=admin_headers,
                               json={"pnl": 999999})
    assert changed.status_code == 409
    assert ledger.list_option_positions(path)[0]["pnl"] == closed["net_pnl"]


def test_position_modes_filter_generic_and_option_rows(app_client, admin_headers, tmp_path, monkeypatch):
    from Backend.application import position_store

    seed_option(tmp_path, monkeypatch)
    paper = position_store.create_open_position({
        "symbol": "TEST-PAPER", "side": "BUY", "quantity": 1,
        "entry_price": 100, "execution_mode": "paper",
    })
    live = position_store.create_open_position({
        "symbol": "TEST-LIVE", "side": "BUY", "quantity": 1,
        "entry_price": 200, "execution_mode": "live",
    })
    paper_headers = {**admin_headers, "X-QuantGrid-Mode": "paper"}
    live_headers = {**admin_headers, "X-QuantGrid-Mode": "live"}
    paper_rows = app_client.get("/positions/open", headers=paper_headers).json()["positions"]
    live_rows = app_client.get("/positions/open", headers=live_headers).json()["positions"]
    assert {row["id"] for row in paper_rows} == {paper["id"], -1}
    assert {row["id"] for row in live_rows} == {live["id"]}
    assert app_client.get("/positions/summary", headers=paper_headers).json()["open_positions"] == 2
    assert app_client.get("/positions/summary", headers=live_headers).json()["current_exposure"] == 200
