from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from Backend.application.options import auto_paper_execution as service
from Backend.application.options.paper_order_ledger import list_option_positions
from Backend.application.options import paper_order_ledger as ledger


NOW = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


@pytest.fixture
def execution(monkeypatch, tmp_path):
    path = tmp_path / "options.sqlite3"
    monkeypatch.setenv("QUANTGRID_OPTION_PAPER_LEDGER", str(path))
    monkeypatch.setenv("QUANTGRID_MAX_ORDER_NOTIONAL", "100000")
    monkeypatch.setenv("QUANTGRID_OPTION_PAPER_STOP_LOSS_PCT", "20")
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(ledger, "datetime", Clock)
    monkeypatch.setattr(service, "get_market_session", lambda: SimpleNamespace(market_live=True))
    monkeypatch.setattr(service, "kill_switch_status", lambda **kwargs: {"active": False})
    account = {"capital": 100000, "risk_per_trade_amount": 1000, "risk_per_trade_pct": 1,
               "max_quantity": 1800, "open_positions": 0, "max_open_positions": 3,
               "trades_today": 0, "max_trades_per_day": 3, "daily_pnl": 0,
               "max_daily_loss": 3000, "weekly_pnl": 0, "max_weekly_loss": 9000,
               "consecutive_losses": 0, "max_consecutive_losses": 2}
    monkeypatch.setattr(service, "risk_status", lambda **kwargs: dict(account))
    selected = []

    def select(spot, side, *, strike=None):
        selected.append((spot, side))
        return {"symbol": "NIFTY", "security_id": "12345" if side == "CE" else "23456",
                "side": side, "expiry": "2026-11-24", "strike": float(strike or 25000), "lot_size": 65}

    monkeypatch.setattr(service, "select_contract", select)
    quote = {"ask": 50.0, "bid": 49.0, "ask_quantity": 1300, "bid_quantity": 1300,
             "quote_timestamp": NOW.isoformat(), "quote_source": "dhan-marketfeed-quote"}
    monkeypatch.setattr(service, "contract_quotes", lambda ids: {value: {**quote, "security_id": value} for value in ids})
    signal = SimpleNamespace(strategy_name="breakout", symbol="NIFTY", side="BUY",
                             entry_price=25000.0, signal_time=NOW, metadata={"quantity": 1})
    return SimpleNamespace(path=path, signal=signal, quote=quote, selected=selected, account=account)


@pytest.mark.parametrize(("direction", "option_type"), [("BUY", "CE"), ("SELL", "PE")])
def test_underlying_direction_buys_option_with_premium_and_master_lot(execution, direction, option_type):
    execution.signal.side = direction
    result = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)

    assert result["status"] == "paper_simulated"
    assert result["order"]["option_type"] == option_type
    assert result["order"]["side"] == "BUY"
    assert result["order"]["price"] == 50
    assert result["order"]["quantity"] == 65
    assert result["order"]["stop_loss"] == 40
    assert result["order"]["target_price"] == 70
    assert execution.selected == [(25000.0, option_type)]
    row = list_option_positions(execution.path)[0]
    assert row["entry_price"] * row["quantity"] == 3250
    assert row["status"] == "open"


def test_signal_retry_returns_original_premium_and_one_record(execution):
    first = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    execution.quote["ask"] = 51
    replay = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)

    assert replay["paper_trade_id"] == first["paper_trade_id"]
    assert replay["order"]["price"] == 50
    assert replay["replayed"] is True
    assert len(list_option_positions(execution.path)) == 1


def test_unaffordable_lot_is_no_trade(execution):
    execution.quote.update(ask=300.0, bid=299.0)
    result = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    assert result["status"] == "no_trade"
    assert result["reason"] == "option_lot_exceeds_budget_or_depth"
    assert list_option_positions(execution.path) == []


def test_kill_switch_prevents_quote_and_persistence(execution, monkeypatch):
    monkeypatch.setattr(service, "kill_switch_status", lambda **kwargs: {"active": True})
    result = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    assert result["reason"] == "KILL_SWITCH_ACTIVE"
    assert execution.selected == []
    assert list_option_positions(execution.path) == []


def test_monitor_exit_uses_option_bid_and_releases_exposure(execution):
    service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    execution.quote.update(bid=70.0, ask=71.0)
    result = service.monitor_option_positions()
    assert result["closed"][0]["exit_reason"] == "target_hit"
    assert result["closed"][0]["exit_price"] == 70
    assert result["closed"][0]["gross_pnl"] == 1300
    assert result["closed"][0]["pnl"] == round(1300 - result["closed"][0]["total_costs"], 2)
    assert list_option_positions(execution.path)[0]["status"] == "closed"


def test_manual_exit_uses_fresh_option_bid_and_is_idempotent(execution):
    first = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    execution.quote.update(bid=45.0, ask=46.0)
    closed = service.exit_option_paper(first["option_order_id"])
    assert closed["exit_price"] == 45
    assert closed["gross_pnl"] == -325
    assert closed["pnl"] < -325
    execution.quote.update(bid=40.0)
    assert service.exit_option_paper(first["option_order_id"])["pnl"] == closed["pnl"]


def test_atomic_global_account_position_limit(execution):
    execution.account["max_open_positions"] = 1
    first = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    execution.signal.strategy_name = "crt_tbs"
    second = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    assert first["status"] == "paper_simulated"
    assert second["reason"] == "MAX_OPEN_POSITIONS_EXCEEDED"
    assert len(list_option_positions(execution.path)) == 1


def test_option_win_resets_earlier_generic_loss_streak(execution):
    first = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    ledger.close_option_position(execution.path, first["option_order_id"], 70, "target_hit")
    execution.account.update(consecutive_losses=2, closed_outcomes=[
        {"closed_at": "2026-11-23T04:00:00+00:00", "pnl": -100},
        {"closed_at": "2026-11-23T04:30:00+00:00", "pnl": -100},
    ])
    execution.signal.strategy_name = "crt_tbs"
    second = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    assert second["status"] == "paper_simulated"


def test_manual_buy_preserves_requested_lots_and_request_identity(execution):
    first = service.submit_manual_option_paper(
        actor_id="user:1", key="manual-request-000001", strike=25100, side="PE", lots=1,
    )
    assert first["status"] == "paper_simulated"
    assert first["order"]["strike"] == 25100
    assert first["order"]["option_type"] == "PE"
    assert first["order"]["quantity"] == 65
    replay = service.submit_manual_option_paper(
        actor_id="user:1", key="manual-request-000001", strike=25100, side="PE", lots=1,
    )
    assert replay["replayed"] is True
    assert replay["paper_trade_id"] == first["paper_trade_id"]
    conflict = service.submit_manual_option_paper(
        actor_id="user:1", key="manual-request-000001", strike=25200, side="PE", lots=1,
    )
    assert conflict["reason"] == "idempotency_key_conflict"
    assert len(list_option_positions(execution.path)) == 1


def test_manual_buy_rejects_unaffordable_requested_lots(execution):
    result = service.submit_manual_option_paper(
        actor_id="user:1", key="manual-request-000001", strike=25000, side="CE", lots=2,
    )
    assert result["reason"] == "option_lot_exceeds_budget_or_depth"
    assert list_option_positions(execution.path) == []


def test_expired_position_requires_review_and_zero_settlement_is_audited(execution, monkeypatch):
    import sys

    first = service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2026, 11, 25, 5, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "get_market_session", lambda: SimpleNamespace(market_live=False))
    monitored = service.monitor_option_positions()
    assert monitored["open"] == 1
    assert monitored["errors"][0]["reason"] == "expired_contract_requires_verified_settlement"
    assert list_option_positions(execution.path)[0]["recovery_reason"]
    with pytest.raises(ValueError, match="reviewed_settlement_evidence_required"):
        service.settle_expired_option_paper(first["option_order_id"], final_underlying_price=24900,
                                            evidence_reference="", actor_id="user:1")
    closed = service.settle_expired_option_paper(first["option_order_id"], final_underlying_price=24900,
                                                evidence_reference="Reviewed NSE final settlement 2026-11-24", actor_id="user:1")
    assert closed["status"] == "closed"
    assert closed["exit_price"] == 0
    assert closed["gross_pnl"] == -3250
    assert closed["settlement_source"] == "manual_final_settlement"
    assert closed["settlement_actor"] == "user:1"
    assert closed["recovery_reason"] is None


def test_failed_square_off_is_retried_for_active_contract(execution, monkeypatch):
    import sys

    service.execute_option_paper(execution.signal, capital=100000, risk_pct=1, rr_ratio=2)
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc))

    def unavailable(ids):
        raise OSError("provider unavailable")

    monkeypatch.setattr(service, "contract_quotes", unavailable)
    assert service.monitor_option_positions()["errors"][0]["reason"] == "option_exit_quote_unavailable"
    assert list_option_positions(execution.path)[0]["status"] == "open"
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2026, 11, 24, 4, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "contract_quotes", lambda ids: {value: {**execution.quote, "security_id": value} for value in ids})
    recovered = service.monitor_option_positions()
    assert recovered["closed"][0]["exit_reason"] == "overdue_square_off"
