from pathlib import Path


def test_live_mode_warning_is_rendered_in_frontend():
    root = Path(__file__).resolve().parents[1]
    topbar = (root / "apps" / "frontend" / "src" / "components" / "Topbar.tsx").read_text(encoding="utf-8")
    execution_form = (root / "apps" / "frontend" / "src" / "components" / "ExecutionForm.tsx").read_text(encoding="utf-8")

    assert 'mode === "live"' in topbar
    assert "LIVE TRADING ENABLED" in topbar
    assert "LIVE TRADING ENABLED" in execution_form


def test_option_chain_renders_dhan_operator_diagnostics():
    root = Path(__file__).resolve().parents[1]
    option_chain = (root / "apps" / "frontend" / "src" / "pages" / "OptionChain.tsx").read_text(encoding="utf-8")

    assert "Dhan Diagnostics" in option_chain
    assert "Likely causes" in option_chain
    assert "Next actions" in option_chain
    assert "profile_login_can_pass" in option_chain
    assert "Profile success does not guarantee Option Chain access" in option_chain
