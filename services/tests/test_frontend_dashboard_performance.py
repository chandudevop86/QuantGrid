from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_routes_are_code_split_and_dashboard_includes_recent_signals():
    app = (ROOT / "apps/frontend/src/App.tsx").read_text(encoding="utf-8")
    dashboard = (ROOT / "apps/frontend/src/pages/Dashboard.tsx").read_text(encoding="utf-8")
    recent = (ROOT / "apps/frontend/src/components/RecentSignals.tsx").read_text(encoding="utf-8")

    assert 'import { lazy, Suspense } from "react"' in app
    assert app.count("lazy(() => import(") >= 20
    assert "<Suspense fallback={<LoadingSkeleton />}" in app
    assert "<RecentSignals limit={signalLimit} />" in dashboard
    assert "api.latestSignals()" in recent
    assert "slice(0, Math.max(1, limit))" in recent
    assert "Loading recent signals" in recent
    assert "No recent signals" in recent
    assert "Recent signals could not be loaded" in recent
