from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_institutional_dashboard_does_not_render_missing_values_as_zero():
    source = (ROOT / "apps/frontend/src/pages/InstitutionalDashboard.tsx").read_text(encoding="utf-8")
    formatter = source.split("function formatNumber", 1)[1].split("function formatUpdated", 1)[0]

    assert 'value === null || value === undefined || value === ""' in formatter
    assert 'return "-"' in formatter
    assert "Number(value)" in formatter
    assert "env_name?: string" in source
    assert 'Set ${item.env_name ?? "env input"}' in source
