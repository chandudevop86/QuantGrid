from datetime import datetime
from types import SimpleNamespace

import pytest
from Backend.domain.models.signal import StrategySignal


def test_worker_persists_lot_constrained_paper_quantity(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    signal = StrategySignal(
        strategy_name="breakout",
        symbol="NIFTY",
        side="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        signal_time=datetime.fromisoformat("2026-05-22T10:00:00+05:30"),
        metadata={"quantity": 70, "score": 9},
    )
    saved = []
    monkeypatch.setattr(worker, "create_paper_trade", lambda payload: saved.append(payload) or {"id": 123})

    trades = worker._generate_paper_trades([signal])

    assert len(trades) == 1
    assert trades[0]["status"] == "paper_simulated"
    assert trades[0]["order"]["quantity"] == 65
    assert trades[0]["paper_trade_id"] == 123
    assert len(saved) == 1
    assert saved[0]["quantity"] == 65


def test_worker_does_not_report_simulation_without_saved_id(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    signal = SimpleNamespace(
        strategy_name="breakout", symbol="NIFTY", side="BUY",
        entry_price=100.0, stop_loss=95.0, target_price=110.0,
        signal_time=datetime.fromisoformat("2026-05-22T10:00:00+05:30"),
        metadata={"quantity": 65}, trailing_stop_loss=None, trailing_stop_pct=None,
    )
    monkeypatch.setattr(worker, "create_paper_trade", lambda payload: {})

    with pytest.raises(KeyError, match="id"):
        worker._generate_paper_trades([signal])


def test_worker_rejected_quantity_reports_reason_without_persistence(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    signal = SimpleNamespace(symbol="NIFTY", entry_price=25000.0, metadata={"quantity": 65})
    monkeypatch.setenv("QUANTGRID_MAX_ORDER_NOTIONAL", "100000")
    monkeypatch.setenv("QUANTGRID_MARGIN_MULTIPLIER", "1")
    monkeypatch.setenv("QUANTGRID_LOT_SIZE_NIFTY", "65")
    saved = []
    monkeypatch.setattr(worker, "create_paper_trade", lambda payload: saved.append(payload))

    trades = worker._generate_paper_trades([signal])

    assert trades[0]["status"] == "no_trade"
    assert trades[0]["reason"] == "margin_limit_exceeded"
    assert trades[0]["required_margin"] == 1625000.0
    assert saved == []


def test_auto_paper_diagnostics_count_rejections_separately(monkeypatch, caplog):
    from Backend.application import worker

    analysis = {"signals": [{}], "trades": [
        {"status": "no_trade", "reason": "quantity_below_one_lot"},
    ]}
    monkeypatch.setattr(worker, "run_live_analysis", lambda payload: analysis)

    with caplog.at_level("INFO"):
        result = worker._run_auto_paper_job({"symbol": "NIFTY", "strategies": ["breakout"]})

    assert result is analysis
    assert "persisted_paper_trades=0 no_trade=1" in caplog.text
    assert "quantity_below_one_lot" in caplog.text
