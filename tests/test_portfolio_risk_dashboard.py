from __future__ import annotations

from datetime import datetime, timedelta, timezone

import Backend.application.portfolio_risk as portfolio_risk
from conftest import admin_headers


def test_portfolio_risk_dashboard_computes_period_pnl_and_sizing(monkeypatch):
    now = datetime.now(timezone.utc)

    monkeypatch.setattr(
        portfolio_risk, "risk_status",
        lambda: {
            "daily_pnl": -250,
            "trades_today": 1,
            "capital": 100000,
            "risk_per_trade_pct": 1,
            "risk_per_trade_amount": 1000,
            "open_positions": 1,
            "current_exposure": 25000,
            "realized_pnl": 500,
            "unrealized_pnl": -100,
            "max_daily_loss": 3000,
            "max_trades_per_day": 3,
            "max_open_positions": 3,
            "max_quantity": 1800,
            "risk_configured": True,
        },
    )
    monkeypatch.setattr(
        portfolio_risk, "position_summary",
        lambda: {
            "open_positions": 1,
            "closed_positions": 1,
            "current_exposure": 25000,
            "realized_pnl": 500,
            "unrealized_pnl": -100,
            "todays_pnl": -250,
        },
    )
    monkeypatch.setattr(
        portfolio_risk, "list_open_positions",
        lambda: [{"symbol": "NIFTY", "side": "BUY", "quantity": 50, "entry_price": 500, "current_price": 500}],
    )
    monkeypatch.setattr(
        portfolio_risk, "list_trade_journal",
        lambda limit: [
            {"pnl": 700, "closed_at": (now - timedelta(days=2)).isoformat()},
            {"pnl": -200, "closed_at": (now - timedelta(days=20)).isoformat()},
        ],
    )
    monkeypatch.setattr(portfolio_risk, "_atr", lambda symbol: 20.0)

    payload = portfolio_risk.build_portfolio_risk_dashboard("NIFTY", entry_price=500, stop_loss=480)

    assert payload["module"] == "portfolio_risk"
    assert payload["pnl"]["daily"] == -250
    assert payload["pnl"]["weekly"] == 600
    assert payload["pnl"]["monthly"] == 400
    assert payload["position_sizing"]["fixed_risk"]["quantity"] == 50
    assert payload["position_sizing"]["atr_based"]["quantity"] == 33
    assert payload["exposure"]["utilization_pct"] == 16.67
    assert payload["checks"]["exposure_limit"] is True


def test_portfolio_risk_dashboard_api_contract(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/risk/dashboard?symbol=NIFTY&entry_price=100&stop_loss=95", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["module"] == "portfolio_risk"
    assert {"daily", "weekly", "monthly"} <= set(payload["pnl"])
    assert {"fixed_risk", "atr_based"} <= set(payload["position_sizing"])
    assert {"daily_loss", "max_open_trades", "exposure_limit"} <= set(payload["checks"])

