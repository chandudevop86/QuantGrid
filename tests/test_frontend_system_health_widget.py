from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_system_health_widget_distinguishes_degraded_api_from_offline():
    widget = (ROOT / "apps/frontend/src/components/SystemHealthWidget.tsx").read_text(encoding="utf-8")

    assert "function healthDegraded" in widget
    assert 'status: apiHealthy ? "Healthy" : apiDegraded ? "Degraded" : "Offline"' in widget
    assert 'tone: apiHealthy ? "green" : apiDegraded ? "yellow" : "red"' in widget
    assert "/api/health reachable; one subsystem needs attention" in widget


def test_strategies_page_marks_websocket_fallback_as_polling():
    strategies = (ROOT / "apps/frontend/src/pages/Strategies.tsx").read_text(encoding="utf-8")

    assert 'websocketStatus={socketConnected ? "online" : "polling"}' in strategies
