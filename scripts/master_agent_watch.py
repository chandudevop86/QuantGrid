"""Scheduled read-only master-agent repo watch.

GitHub Actions is best effort, not a guaranteed continuous service.
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

SENSITIVE_PATTERNS = (
    ("private_key", "-----BEGIN PRIVATE KEY-----"),
    ("aws_access_key", "AKIA"),
)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}


def scan_repository(root: Path) -> dict:
    findings = []
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".env"}:
            continue
        if path.stat().st_size > 512_000:
            continue
        checked += 1
        try:
            contents = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        for label, pattern in SENSITIVE_PATTERNS:
            if pattern in contents:
                findings.append({"path": str(path.relative_to(root)), "type": label})
    return {"checked_files": checked, "findings": findings}


def render_report(result: dict) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = ["# QuantGrid Master Agent Watch", "", f"Run UTC: {now}",
             f"Files inspected: {result['checked_files']}",
             f"Potential secret markers: {len(result['findings'])}", "",
             "This is a read-only heuristic scan. No production telemetry, broker accounts, "
             "live market feeds or client data were accessed. Results require review.", ""]
    for item in result["findings"][:30]:
        lines.append(f"- {item['type']}: \`{item['path']}\` (review; no secret contents shown)")
    return "\\n".join(lines) + "\\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="master-agent-report.md")
    args = parser.parse_args()
    Path(args.output).write_text(render_report(scan_repository(Path.cwd())), encoding="utf-8")


if __name__ == "__main__":
    main()
