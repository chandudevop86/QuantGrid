from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLES_TS = ROOT / "apps" / "frontend" / "src" / "roles.ts"


def _roles_source() -> str:
    return ROLES_TS.read_text(encoding="utf-8")


def test_trader_navigation_stays_focused_on_decision_workflow():
    source = _roles_source()
    for route in ("/", "/market", "/signals", "/paper-trades", "/history", "/settings", "/subscription"):
        assert f'"{route}": ["admin", "developer", "trader", "analyst", "viewer", "ops"]' in source


def test_advanced_routes_are_developer_mode_only():
    source = _roles_source()
    advanced_routes = [
        "/candles",
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


def test_duplicate_page_routes_redirect_to_one_canonical_destination():
    app = (ROOT / "apps" / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert 'path="/backtesting" element={<Navigate to="/history" replace />}' in app
    assert 'path="/live" element={<Navigate to="/strategies" replace />}' in app
    assert 'path="/analysis" element={<Navigate to="/strategies" replace />}' in app
    assert 'path="/option-chain" element={<Navigate to="/market" replace />}' in app
    assert 'path="/risk" element={<Navigate to="/settings" replace />}' in app
    assert app.count("<Backtesting />") == 1
    assert "<LiveAnalysis />" not in app
    assert app.count("<OptionChain />") == 1
    assert app.count("<RiskDashboard />") == 1
