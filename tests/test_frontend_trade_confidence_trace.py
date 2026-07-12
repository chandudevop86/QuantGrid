from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_renders_canonical_trade_confidence_factor_trace_in_advanced_panel():
    dashboard = (ROOT / "apps/frontend/src/pages/Dashboard.tsx").read_text(encoding="utf-8")

    assert "Trade Confidence Factors" in dashboard
    assert "trade_confidence?.meaning" in dashboard
    assert "trade_confidence?.factors" in dashboard
    assert "factor.contribution" in dashboard
    assert "factor.weight" in dashboard
    assert "factor.source" in dashboard
    assert "formatTime(factor.timestamp)" in dashboard
    assert dashboard.index("Trade Confidence Factors") > dashboard.index('summary>Advanced evidence and diagnostics')
