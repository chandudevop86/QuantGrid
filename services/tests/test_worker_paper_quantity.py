from datetime import datetime
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
    monkeypatch.setattr(worker, "create_paper_trade", lambda payload: saved.append(payload))

    trades = worker._generate_paper_trades([signal])

    assert len(trades) == 1
    assert trades[0]["status"] == "paper_simulated"
    assert trades[0]["order"]["quantity"] == 65
    assert len(saved) == 1
    assert saved[0]["quantity"] == 65
