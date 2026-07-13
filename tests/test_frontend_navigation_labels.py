from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_default_navigation_uses_unambiguous_product_labels():
    sidebar = (ROOT / "apps" / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")

    expected = {
        'to: "/", label: "Dashboard"',
        'to: "/market", label: "Market"',
        'to: "/strategies", label: "Strategies"',
        'to: "/trade", label: "Orders"',
        'to: "/paper-trades", label: "Positions"',
        'to: "/trade-journal", label: "History"',
        'to: "/settings", label: "Risk"',
        'to: "/subscription", label: "Settings"',
    }
    assert all(item in sidebar for item in expected)
    assert 'label: "Risk & Settings"' not in sidebar
    assert 'to: "/history", label: "History"' not in sidebar


def test_default_navigation_remains_focused_and_advanced_routes_remain_available():
    sidebar = (ROOT / "apps" / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    default_block = sidebar.split("const primaryItems: NavItem[] = [", 1)[1].split("];", 1)[0]
    advanced_block = sidebar.split("const advancedItems: NavItem[] = [", 1)[1].split("];", 1)[0]
    admin_block = sidebar.split("const adminItems: NavItem[] = [", 1)[1].split("];", 1)[0]

    assert default_block.count("{ to:") == 8
    assert 'to: "/candles"' in advanced_block
    assert 'to: "/signals"' in advanced_block
    assert 'to: "/security"' in advanced_block
    assert 'to: "/operations"' in admin_block
    assert 'to: "/admin/users"' in admin_block
    assert "allowedAdvanced" in sidebar
    assert "advancedOpen" in sidebar
    assert "qg-mobile-more" in sidebar
    assert 'aria-controls="qg-mobile-navigation"' in sidebar
