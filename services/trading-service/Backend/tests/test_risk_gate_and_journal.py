from __future__ import annotations

import sqlite3

from Backend.application import kill_switch, paper_trade_store
from Backend.application.risk_gate import evaluate_risk_gate
from Backend.application.signal_quality import SignalDecision


def test_paper_trade_creation_and_risk_gate_daily_loss(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    monkeypatch.setattr(paper_trade_store, "_connect", lambda: connection)
    monkeypatch.setattr(kill_switch, "_connect", lambda: connection)
    monkeypatch.setenv("QUANTGRID_MAX_DAILY_LOSS", "100")

    trade = paper_trade_store.create_paper_trade({
        "strategy": "test",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100,
        "stop_loss": 95,
        "target": 110,
        "status": "closed",
        "pnl": -150,
        "score": 8,
        "regime": "TRENDING",
    })

    decision = SignalDecision(True, "ACTIVE", "OK", 0.0, "2026-05-22T03:00:00+00:00", 8, "TRENDING", "BULLISH")
    gate = evaluate_risk_gate(decision)

    assert trade["id"] > 0
    assert gate.allowed is False
    assert gate.reason == "DAILY_LOSS_LIMIT"
    connection.close()
