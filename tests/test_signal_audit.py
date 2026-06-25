from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from Backend.application.signal_audit import StrategyAuditInput, audit_strategy, normalize_rejection_reason
from Backend.domain.models.signal import StrategySignal


def _signal(**overrides):
    data = {
        "strategy_name": "Breakout",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target_price": 110.0,
        "signal_time": datetime(2026, 6, 25, 10, 0),
        "metadata": {"score": 8.0},
    }
    data.update(overrides)
    return StrategySignal(**data)


def _input(raw=None, validated=None, paper_count=0):
    return StrategyAuditInput(
        key="breakout",
        label="Breakout",
        raw_signals=list(raw or []),
        validated_signals=list(validated or []),
        candles=[{"timestamp": "2026-06-25T10:00:00Z", "open": 1, "high": 2, "low": 1, "close": 2}],
        trend_candles=[],
        candle_source="yahoo-finance",
        candle_validation=SimpleNamespace(valid_for_execution=True, market_status="LIVE MARKET"),
        paper_trade_created_count=paper_count,
    )


def test_audit_counts_raw_signal_generated():
    signal = _signal()

    row = audit_strategy(_input(raw=[signal], validated=[]))

    assert row["raw_signal_count"] == 1
    assert row["validated_signal_count"] == 0
    assert row["lifecycle"]["RAW_SIGNAL"] == 1


def test_audit_neutral_signal_when_no_raw_setup():
    row = audit_strategy(_input())

    assert row["latest_signal"] == "NEUTRAL"
    assert row["rejection_reason"] == "NEUTRAL"
    assert row["execution_decision"] == "NO_RAW_SIGNAL"


def test_audit_rejects_low_confidence_signal():
    signal = _signal(metadata={"score": 4.0})

    row = audit_strategy(_input(raw=[signal], validated=[]))

    assert row["rejection_reason"] == "LOW_CONFIDENCE"
    assert row["rejected_signal_count"] == 1


def test_audit_rejects_missing_risk_reward():
    signal = _signal(target_price=101.0, metadata={"score": 9.0})

    row = audit_strategy(_input(raw=[signal], validated=[]))

    assert row["rejection_reason"] == "MISSING_RISK_REWARD"
    assert normalize_rejection_reason("anything", signal) == "MISSING_RISK_REWARD"


def test_audit_marks_validated_buy_sell_signal_ready(monkeypatch):
    import Backend.application.signal_audit as signal_audit

    monkeypatch.setattr(
        signal_audit,
        "decide_signal",
        lambda *args, **kwargs: SimpleNamespace(allowed=True, reason="OK", to_dict=lambda: {"allowed": True, "reason": "OK"}),
    )
    monkeypatch.setattr(signal_audit, "evaluate_risk_gate", lambda decision: SimpleNamespace(allowed=True, reason="OK"))
    monkeypatch.setattr(signal_audit, "validate_order_risk", lambda *args, **kwargs: SimpleNamespace(allowed=True, reason="OK"))

    buy = _signal(side="BUY")
    sell = _signal(side="SELL", entry_price=100, stop_loss=105, target_price=90)

    buy_row = audit_strategy(_input(raw=[buy], validated=[buy]))
    sell_row = audit_strategy(_input(raw=[sell], validated=[sell]))

    assert buy_row["accepted_signal_count"] == 1
    assert sell_row["latest_signal"] == "SELL"
    assert sell_row["execution_decision"] == "READY_FOR_PAPER_TRADE"


def test_audit_tracks_paper_trade_created_lifecycle():
    signal = _signal()

    row = audit_strategy(_input(raw=[signal], validated=[], paper_count=2))

    assert row["paper_trade_created_count"] == 2
    assert row["lifecycle"]["PAPER_TRADE_CREATED"] == 2


def test_system_audit_summarizes_data_logic_and_trade_block(monkeypatch):
    import Backend.presentation.api.professional_api as professional_api

    monkeypatch.setattr(
        professional_api,
        "get_price",
        lambda symbol: {"symbol": symbol, "price": 22500, "source": "broker"},
    )
    monkeypatch.setattr(
        professional_api,
        "_build_signal_audit",
        lambda symbol: {
            "symbol": symbol,
            "data": {
                "candle_count": 100,
                "candle_age_seconds": 15,
                "valid_for_analysis": True,
                "valid_for_execution": True,
                "using_fallback_data": False,
                "market_status": "LIVE MARKET",
            },
            "strategies": [
                {"strategy": "Breakout", "raw_signal_count": 1, "validated_signal_count": 0, "rejection_reason": "LOW_CONFIDENCE"}
            ],
            "lifecycle_totals": {
                "RAW_SIGNAL": 1,
                "VALIDATED_SIGNAL": 0,
                "ACCEPTED_SIGNAL": 0,
                "REJECTED_SIGNAL": 1,
                "PAPER_TRADE_CREATED": 0,
            },
        },
    )

    payload = professional_api.system_audit(symbol="NIFTY")

    assert payload["data_status"] == "OK"
    assert payload["data_ok"] is True
    assert payload["logic_ok"] is True
    assert payload["raw_signals"] == 1
    assert payload["validated_signals"] == 0
    assert payload["rejected_signals"] == 1
    assert payload["trades_created"] == 0
    assert "LOW_CONFIDENCE" in payload["trade_not_created_because"]
