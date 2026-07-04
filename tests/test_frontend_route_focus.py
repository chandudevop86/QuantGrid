from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLES_TS = ROOT / "apps" / "frontend" / "src" / "roles.ts"


def _roles_source() -> str:
    return ROLES_TS.read_text(encoding="utf-8")


def test_trader_navigation_stays_focused_on_decision_workflow():
    source = _roles_source()
    for route in ("/", "/market", "/signals", "/paper-trades", "/history", "/settings"):
        assert f'"{route}": ["admin", "developer", "trader", "analyst", "viewer", "ops"]' in source


def test_advanced_routes_are_developer_mode_only():
    source = _roles_source()
    advanced_routes = [
        "/candles",
        "/backtesting",
        "/copilot",
        "/operations",
        "/institutional",
        "/strategies",
        "/trading-engine",
        "/trade",
    ]
    for route in advanced_routes:
        line = next(item for item in source.splitlines() if item.strip().startswith(f'"{route}"'))
        assert '"trader"' not in line
        assert '"viewer"' not in line
        assert '"analyst"' not in line
