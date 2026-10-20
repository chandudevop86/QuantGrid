from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps" / "frontend" / "src"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v3_uses_integrated_shell_without_fake_market_quotes():
    layout = read("layouts/AppLayout.tsx")
    assert "WorkspaceCommandPalette" in layout
    assert "No verified current market quote is available" in layout
    assert "last_candle_timestamp" in layout
    assert "socketStatus" in layout
    assert "market_status" in layout
    assert "24,672.35" not in layout
    assert "55,342.10" not in layout
    assert "Risk remains contained" not in layout
    assert "Market breadth is positive" not in layout
    assert "42%" not in layout
    assert "WorkspaceContext" in layout


def test_v3_styles_are_loaded_last_and_support_mobile_and_accessibility():
    entry = read("main.tsx")
    assert entry.index('import "./index.css";') < entry.index('import "./workspace-v3.css";')
    css = read("workspace-v3.css")
    assert ".qg-workspace-v3" in css
    assert "@media (max-width: 1100px)" in css
    assert "@media (max-width: 760px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css


def test_v3_quick_navigation_only_exposes_authorized_routes():
    palette = read("components/WorkspaceCommandPalette.tsx")
    assert "canAccessRoute" in palette
    assert "canAccess(destination.entitlement)" in palette
    assert "hasAuthToken()" in palette
    assert 'role="dialog"' in palette
    assert 'aria-modal="true"' in palette
    assert "onClose()" in palette
    layout = read("layouts/AppLayout.tsx")
    assert 'event.key.toLowerCase() === "k"' in layout


def test_v3_preserves_existing_paper_live_visibility_and_role_guarding():
    header = read("components/AppHeader.tsx")
    sidebar = read("components/Sidebar.tsx")
    assert 'mode === "live"' in header
    assert "Live trading mode is enabled." in header
    assert 'className={mode === "live" ? "active live" : ""}' in header
    assert "canAccessRoute(role, item.to)" in sidebar
    assert "canAccess(item.entitlement)" in sidebar
    assert "qg-mobile-more" in sidebar


def test_v3_dashboard_does_not_claim_live_when_market_is_closed():
    dashboard = read("pages/Dashboard.tsx")
    assert "useMarketSelection" in dashboard
    assert "marketLabel" in dashboard
    assert "sessionIsOpen" in dashboard
    assert 'is-closed' in dashboard
