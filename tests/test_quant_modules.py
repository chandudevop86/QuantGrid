from __future__ import annotations

from conftest import admin_headers


def test_quant_modules_dashboard_exposes_four_modules(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/modules/dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"option_chain", "backtesting", "risk_engine", "trade_journal"}
    assert payload["option_chain"]["source"] == "synthetic-demo-chain"
    assert "pcr" in payload["option_chain"]
    assert "max_pain" in payload["option_chain"]
    assert "equity_curve" in payload["backtesting"]
    assert payload["risk_engine"]["state"] in {"normal", "halted"}
    assert "win_rate" in payload["trade_journal"]


def test_backtesting_module_accepts_payload(app_client):
    headers = admin_headers(app_client)
    candles = [
        {"timestamp": "2026-05-22T09:15:00+05:30", "open": 100, "high": 104, "low": 99, "close": 102, "volume": 1000},
        {"timestamp": "2026-05-22T09:20:00+05:30", "open": 102, "high": 106, "low": 101, "close": 105, "volume": 1000},
        {"timestamp": "2026-05-22T09:25:00+05:30", "open": 105, "high": 107, "low": 103, "close": 104, "volume": 1000},
    ]

    response = app_client.post(
        "/modules/backtesting",
        json={"symbol": "NIFTY", "strategy_name": "amd", "candles": candles, "min_score": 0},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "backtesting"
    assert payload["payload"]["candles"] == len(candles)
    assert "recent_outcomes" in payload
