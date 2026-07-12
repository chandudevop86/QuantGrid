from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unused_frontend_compatibility_duplicates_are_removed():
    removed = (
        "apps/frontend/routes.tsx",
        "apps/frontend/src/pages/job.tsx",
        "apps/frontend/src/components/MetricCard.tsx",
        "apps/frontend/src/hooks/AutoSignals.ts",
    )

    assert all(not (ROOT / path).exists() for path in removed)
    assert (ROOT / "apps/frontend/src/App.tsx").exists()
    assert (ROOT / "apps/frontend/src/pages/Jobs.tsx").exists()
    assert (ROOT / "apps/frontend/src/hooks/useAutoSignals.ts").exists()
