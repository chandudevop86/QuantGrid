import logging

from Backend.application import worker


def test_auto_paper_logs_signal_rejection_reasons(monkeypatch, caplog):
    def fake_run_live_analysis(payload):
        assert payload.auto_trade is True
        assert payload.execution_mode == "paper"
        return {
            "signals": [],
            "rejected_signals": [
                {"decision": {"reason": "LOW_SCORE"}}
            ],
            "stale_signals": [
                {"decision": {"reason": "STALE_SIGNAL"}}
            ],
            "trades": [],
            "auto_trade_blocked_reason": None,
        }

    monkeypatch.setattr(
        worker,
        "run_live_analysis",
        fake_run_live_analysis,
    )

    with caplog.at_level(logging.INFO):
        result = worker._run_auto_paper_job({
            "symbol": "NIFTY",
            "strategies": ["mtfa"],
        })

    assert result["signals"] == []
    assert "auto_paper_signal_diagnostics" in caplog.text
    assert "strategy=mtfa" in caplog.text
    assert "LOW_SCORE" in caplog.text
    assert "STALE_SIGNAL" in caplog.text
