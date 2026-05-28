from pathlib import Path


def test_live_mode_warning_is_rendered_in_frontend():
    root = Path(__file__).resolve().parents[1]
    topbar = (root / "apps" / "frontend" / "src" / "components" / "Topbar.tsx").read_text(encoding="utf-8")
    execution_form = (root / "apps" / "frontend" / "src" / "components" / "ExecutionForm.tsx").read_text(encoding="utf-8")

    assert 'mode === "live"' in topbar
    assert "LIVE TRADING ENABLED" in topbar
    assert "LIVE TRADING ENABLED" in execution_form
