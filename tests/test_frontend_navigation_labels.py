from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_default_navigation_uses_unambiguous_product_labels():
    sidebar = (ROOT / "apps" / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")

    expected = {
        'to: "/", label: "Market Decision"',
        'to: "/market", label: "Options Market"',
        'to: "/signals", label: "Qualified Setups"',
        'to: "/paper-trades", label: "Paper Portfolio"',
        'to: "/history", label: "Backtest Results"',
        'to: "/settings", label: "Risk Controls"',
        'to: "/subscription", label: "Plan & Access"',
    }
    assert all(item in sidebar for item in expected)
    assert 'label: "Risk & Settings"' not in sidebar
    assert 'to: "/history", label: "History"' not in sidebar


def test_default_navigation_remains_focused_and_advanced_routes_remain_available():
    sidebar = (ROOT / "apps" / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    default_block = sidebar.split("const navItems = [", 1)[1].split("];", 1)[0]
    advanced_block = sidebar.split("const advancedItems = [", 1)[1].split("];", 1)[0]

    assert default_block.count("{ to:") == 7
    assert 'to: "/operations"' in advanced_block
    assert 'to: "/security"' in advanced_block
    assert 'to: "/strategies"' in advanced_block
