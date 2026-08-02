from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_renders_canonical_confidence_and_explainability_without_duplicate_gauges():
    dashboard = (ROOT / "apps/frontend/src/pages/Dashboard.tsx").read_text(encoding="utf-8")
    decision_card = (ROOT / "apps/frontend/src/components/DecisionCard.tsx").read_text(encoding="utf-8")
    decision_reasons = (ROOT / "apps/frontend/src/components/DecisionReasons.tsx").read_text(encoding="utf-8")

    assert "finalDecision.trade_confidence?.score" in dashboard
    assert "finalDecision.explainability?.plain_english" in dashboard
    assert "finalDecision.block_reasons" in dashboard
    assert "supporting_factors" in dashboard
    assert "opposing_factors" in dashboard
    assert "Confidence" in decision_card
    assert "Math.round(confidence)" in decision_card
    assert "reasons.slice(0, 4)" in decision_reasons
    assert "Trade Confidence Factors" not in dashboard
