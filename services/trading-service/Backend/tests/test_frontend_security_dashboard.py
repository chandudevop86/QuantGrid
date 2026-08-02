from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_security_dashboard_prioritizes_readable_command_summary():
    source = (ROOT / "apps/frontend/src/pages/Security.tsx").read_text(encoding="utf-8")
    css = (ROOT / "apps/frontend/src/index.css").read_text(encoding="utf-8")

    assert "security-command-strip" in source
    assert "Top Fix" in source
    assert "priorityCards" in source
    assert ".slice(0, 4)" in source
    assert "security-command-strip" in css
    assert "overflow-wrap: anywhere" in css
