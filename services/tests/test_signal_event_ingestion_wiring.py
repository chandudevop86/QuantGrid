"""Scanner event ingestion defaults off and precedes paper trade creation."""
from __future__ import annotations

import ast
from pathlib import Path

from Backend.application.signal_event_ingestion import scanner_event_ingestion_enabled


def test_scanner_event_ingestion_disabled_by_default(monkeypatch):
    monkeypatch.delenv("QUANTGRID_SIGNAL_EVENT_INGESTION", raising=False)
    assert not scanner_event_ingestion_enabled()
    monkeypatch.setenv("QUANTGRID_SIGNAL_EVENT_INGESTION", "true")
    assert scanner_event_ingestion_enabled()


def test_scanner_persists_decisions_before_any_paper_trade_work():
    source = (Path(__file__).resolve().parents[1] / "trading-service" /
              "Backend" / "application" / "live_analysis_worker.py").read_text()
    parsed = ast.parse(source)
    fn = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == "run_live_analysis")
    calls = [
        (n.func.id, n.lineno) for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    ingestion = next(line for name, line in calls if name == "record_scanner_decisions")
    execution = next(line for name, line in calls if name == "_generate_paper_trades")
    assert ingestion < execution
