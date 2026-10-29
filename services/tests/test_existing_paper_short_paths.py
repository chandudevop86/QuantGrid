"""Regression tests for the existing paper SELL accounting paths.

These tests intentionally avoid broker submission and live execution.
"""
from Backend.application.paper_trade_store import (
    calculate_paper_trade_pnl,
    resolve_paper_trade_outcome,
)
from Backend.application.position_store import _open_pnl


def test_short_open_pnl_falls_when_price_rises():
    assert _open_pnl("SELL", 10, 100, 90) == 100
    assert _open_pnl("SELL", 10, 100, 110) == -100


def test_short_realized_pnl_partial_quantity():
    assert calculate_paper_trade_pnl(
        side="SELL", entry=100, exit_price=90, quantity=10, partial_quantity=4
    ) == 40
    assert calculate_paper_trade_pnl(
        side="SELL", entry=100, exit_price=110, quantity=10
    ) == -100


def test_short_target_and_stop_are_directional():
    trade = {
        "side": "SELL", "entry": 100, "stop_loss": 105,
        "target": 90, "quantity": 10, "status": "open",
    }
    target = resolve_paper_trade_outcome(trade, 89)
    assert (target["status"], target["result"], target["pnl"]) == ("closed", "win", 110)
    stop = resolve_paper_trade_outcome(trade, 106)
    assert (stop["status"], stop["result"], stop["pnl"]) == ("closed", "loss", -60)
    pending = resolve_paper_trade_outcome(trade, 99)
    assert pending["status"] == "open"
