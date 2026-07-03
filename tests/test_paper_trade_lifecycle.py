from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application.paper_trade_store import (
    calculate_paper_trade_pnl,
    manual_exit_payload,
    resolve_paper_trade_outcome,
)


def test_resolve_paper_trade_target_and_stop_outcomes():
    trade = {"side": "BUY", "entry": 100, "stop_loss": 95, "target": 110, "quantity": 2, "status": "open"}

    target = resolve_paper_trade_outcome(trade, 111)
    stop = resolve_paper_trade_outcome(trade, 94)
    open_trade = resolve_paper_trade_outcome(trade, 102)

    assert target["status"] == "closed"
    assert target["result"] == "win"
    assert target["exit_reason"] == "target_hit"
    assert target["pnl"] == 22
    assert stop["result"] == "loss"
    assert stop["exit_reason"] == "stop_loss_hit"
    assert open_trade["status"] == "open"


def test_manual_and_partial_exit_payloads_are_deterministic():
    trade = {"side": "BUY", "entry": 100, "stop_loss": 95, "target": 110, "quantity": 4, "status": "open"}

    partial = manual_exit_payload(trade, exit_price=106, quantity=2)
    closed = manual_exit_payload(trade, exit_price=96)

    assert partial["status"] == "partially_exited"
    assert partial["exit_quantity"] == 2
    assert partial["quantity"] == 2
    assert partial["pnl"] == 12
    assert closed["status"] == "closed"
    assert closed["pnl"] == -16
    assert calculate_paper_trade_pnl(side="SELL", entry=100, exit_price=94, quantity=3) == 18
