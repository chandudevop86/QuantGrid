def _seed_option(tmp_path, monkeypatch):
    from Backend.application.options import paper_order_ledger as ledger
    from Backend.presentation.api import positions_api

    path = tmp_path / "option-paper.sqlite3"
    monkeypatch.setenv("QUANTGRID_OPTION_PAPER_LEDGER", str(path))
    monkeypatch.setattr(positions_api, "list_open_positions", lambda: [])
    monkeypatch.setattr(positions_api, "list_closed_positions", lambda: [])
    monkeypatch.setattr(positions_api, "position_summary", lambda: {
        "open_positions": 0, "closed_positions": 0, "current_exposure": 0,
        "realized_pnl": 0, "unrealized_pnl": 0, "todays_pnl": 0,
    })
    result = ledger.record_verified_paper_buy(path, "auto-paper", "test-option-signal-0001", {
        "execution_mode": "paper", "eligible": True,
        "symbol": "NIFTY", "side": "PE", "security_id": "123456",
        "expiry": "2099-12-31", "strike": 25000, "lot_size": 65,
        "lots": 1, "ask": 100.0, "stop_loss": 80.0, "target": 140.0,
    })
    return path, result["order_id"]


def test_option_positions_visible_in_paper_ui_and_summary(app_client, admin_headers, tmp_path, monkeypatch):
    _seed_option(tmp_path, monkeypatch)
    response = app_client.get("/positions/open", headers=admin_headers)
    assert response.status_code == 200
    row = response.json()["positions"][0]
    assert row["id"] < 0
    assert row["option_order_id"] == -row["id"]
    assert row["symbol"].endswith("25000 PE")
    assert row["quantity"] == 65
    assert row["entry_price"] == 100
    assert row["execution_mode"] == "paper"
    summary = app_client.get("/positions/summary", headers=admin_headers).json()
    assert summary["open_positions"] == 1
    assert summary["current_exposure"] == 6500
    live_headers = {**admin_headers, "X-QuantGrid-Mode": "live"}
    assert app_client.get("/positions/open", headers=live_headers).json()["positions"] == []


def test_option_manual_exit_uses_verified_service_price(app_client, admin_headers, tmp_path, monkeypatch):
    from Backend.application.options import auto_paper_execution, paper_order_ledger

    path, order_id = _seed_option(tmp_path, monkeypatch)
    calls = []

    def close(identity, reason):
        calls.append((identity, reason))
        return paper_order_ledger.close_option_position(path, identity, 110.0, reason)

    monkeypatch.setattr(auto_paper_execution, "exit_option_paper", close)
    response = app_client.post(f"/positions/{-order_id}/exit", headers=admin_headers,
                              json={"reason": "manual_exit", "exit_price": 999999})
    assert response.status_code == 200
    row = response.json()["position"]
    assert row["id"] == -order_id
    assert row["exit_price"] == 110
    assert row["closed_pnl"] == 650
    assert calls == [(order_id, "manual_exit")]
    summary = app_client.get("/positions/summary", headers=admin_headers).json()
    assert summary["open_positions"] == 0
    assert summary["closed_positions"] == 1
    assert summary["realized_pnl"] == 650


def test_live_mode_cannot_exit_option_paper_position(app_client, admin_headers, tmp_path, monkeypatch):
    from Backend.application.options import auto_paper_execution

    _, order_id = _seed_option(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(auto_paper_execution, "exit_option_paper", lambda *a, **k: calls.append(a))
    response = app_client.post(f"/positions/{-order_id}/exit",
                              headers={**admin_headers, "X-QuantGrid-Mode": "live"}, json={})
    assert response.status_code == 400
    assert calls == []


def test_exit_all_includes_option_ledger_positions(app_client, admin_headers, tmp_path, monkeypatch):
    from Backend.application.options import auto_paper_execution, paper_order_ledger
    from Backend.presentation.api import positions_api

    path, order_id = _seed_option(tmp_path, monkeypatch)

    async def generic_exit(**kwargs):
        return {"checked": 0, "exited": 0, "positions": [], "errors": []}

    monkeypatch.setattr(positions_api, "exit_all_positions", generic_exit)
    monkeypatch.setattr(auto_paper_execution, "exit_option_paper", lambda identity, reason:
                        paper_order_ledger.close_option_position(path, identity, 95.0, reason))
    response = app_client.post("/positions/exit-all", headers=admin_headers, json={})
    assert response.status_code == 200
    result = response.json()
    assert result["checked"] == result["exited"] == 1
    assert result["errors"] == []
    assert result["positions"][0]["position"]["id"] == -order_id
    assert result["positions"][0]["position"]["closed_pnl"] == -325
