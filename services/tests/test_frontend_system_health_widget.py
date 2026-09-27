from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_system_health_widget_distinguishes_degraded_api_from_offline():
    widget = (ROOT / "apps/frontend/src/components/SystemHealthWidget.tsx").read_text(encoding="utf-8")

    assert "function healthDegraded" in widget
    assert 'status: apiHealthy ? "Healthy" : apiDegraded ? "Degraded" : "Offline"' in widget
    assert 'tone: apiHealthy ? "green" : apiDegraded ? "yellow" : "red"' in widget
    assert "/api/health reachable; one subsystem needs attention" in widget


def test_strategies_page_marks_websocket_fallback_as_polling():
    strategies = (ROOT / "apps/frontend/src/pages/Strategies.tsx").read_text(encoding="utf-8")

    assert 'websocketStatus={socketConnected ? "online" : "polling"}' in strategies


def test_system_health_widget_treats_redis_fallback_as_degraded_not_offline():
    widget = (ROOT / "apps/frontend/src/components/SystemHealthWidget.tsx").read_text(encoding="utf-8")

    assert 'redisFallbackActive' in widget
    assert 'status: health?.redis?.connected ? "Healthy" : redisFallbackActive ? "Fallback"' in widget
    assert 'tone: health?.redis?.connected ? "green" : redisFallbackActive ? "yellow"' in widget


def test_system_health_widget_distinguishes_websocket_idle_from_offline():
    widget = (ROOT / "apps/frontend/src/components/SystemHealthWidget.tsx").read_text(encoding="utf-8")

    assert 'websocketAvailable' in widget
    assert '? "Idle"' in widget
    assert 'Endpoint available; no active clients' in widget
