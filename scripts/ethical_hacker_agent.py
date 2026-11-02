#!/usr/bin/env python3
"""QuantGrid defensive security agent: offline, read-only repository checks."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
PATTERNS = [
    ("SEC001", "HIGH", "Hard-coded private key marker", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("SEC002", "MEDIUM", "Python shell execution with shell=True", re.compile(r"subprocess\.(?:run|Popen|call|check_output)\s*\([\s\S]{0,240}?shell\s*=\s*True")),
    ("SEC003", "MEDIUM", "Python debug mode explicitly enabled", re.compile(r"\bdebug\s*=\s*True\b")),
    ("SEC004", "MEDIUM", "Potentially unsafe pickle deserialization", re.compile(r"\bpickle\.loads?\s*\(")),
]
SCAN_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
MAX_BYTES = 512_000


def scan():
    findings = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in EXCLUDE for part in path.relative_to(ROOT).parts):
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("scripts/ethical_hacker_agent.py") or rel.startswith("services/tests/"):
            continue
        data = path.read_text(encoding="utf-8", errors="replace")
        for rule, severity, message, pattern in PATTERNS:
            for match in pattern.finditer(data):
                line = data.count("\n", 0, match.start()) + 1
                findings.append({"rule": rule, "severity": severity, "file": rel, "line": line, "message": message})
    return sorted(findings, key=lambda x: (x["rule"], x["file"], x["line"]))


def main():
    findings = scan()
    report = {"agent": "quantgrid-ethical-hacker", "mode": "offline-read-only",
              "findings": findings, "count": len(findings)}
    out = ROOT / "ethical-hacker-report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# QuantGrid ethical-hacking agent report", "",
             "**Scope:** Offline repository checks; no network scanning or broker operations.",
             f"**Potential findings:** {len(findings)}", "",
             "| Rule | Severity | Location | Finding |", "|---|---|---|---|"]
    for f in findings[:100]:
        lines.append(f"| {f['rule']} | {f['severity']} | `{f['file']}:{f['line']}` | {f['message']} |")
    if len(findings) > 100:
        lines.append(f"\nOnly first 100 findings shown; JSON contains all {len(findings)}.")
    lines.extend(["", "Findings are heuristic and require manual validation.",
                  "Run CodeQL, Bandit, Gitleaks, pip-audit, Trivy and security regression tests separately.",
                  "Never test third-party broker systems without authorization."])
    summary = "\n".join(lines)
    print(summary)
    import os
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(summary + "\n")


if __name__ == "__main__":
    main()
