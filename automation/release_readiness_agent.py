"""Release-readiness checklist generator for QuantGrid.

This agent is intentionally non-deploying. It consumes a verification report and
prepares a human-review checklist only. It never merges, deploys, changes trading
configuration, accesses secrets, or submits orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MAX_REPORT_BYTES = 65536


def build_release_checklist(verification: dict) -> dict:
    if not isinstance(verification, dict):
        raise ValueError("Verification report must be a JSON object.")
    if verification.get("mode") != "verification-only":
        raise ValueError("Expected a verification-only report.")

    checks = verification.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("Verification report must include at least one check.")

    normalized_checks = []
    incomplete = []
    failed = []

    for item in checks:
        if not isinstance(item, dict):
            raise ValueError("Each verification check must be an object.")
        name = str(item.get("check") or "").strip()
        if not name:
            raise ValueError("Each verification check requires a name.")

        executed = item.get("executed") is True
        returncode = item.get("returncode")
        passed = executed and returncode == 0

        normalized_checks.append(
            {
                "check": name,
                "executed": executed,
                "returncode": returncode,
                "passed": passed,
            }
        )
        if not executed:
            incomplete.append(name)
        elif returncode != 0:
            failed.append(name)

    verification_healthy = verification.get("healthy") is True
    ready_for_human_review = verification_healthy and not incomplete and not failed

    blockers = []
    if not verification_healthy:
        blockers.append("Verification report is not healthy.")
    if incomplete:
        blockers.append("Verification checks not executed: " + ", ".join(incomplete))
    if failed:
        blockers.append("Verification checks failed: " + ", ".join(failed))

    return {
        "mode": "release-checklist-only",
        "ready_for_human_review": ready_for_human_review,
        "verification_checks": normalized_checks,
        "blockers": blockers,
        "checklist": [
            {
                "item": "Review code diff and scope",
                "required": True,
                "completed": False,
                "owner": "human",
            },
            {
                "item": "Confirm CI, security, and code scanning checks are green",
                "required": True,
                "completed": ready_for_human_review,
                "owner": "human",
            },
            {
                "item": "Confirm no live-trading or risk-limit changes",
                "required": True,
                "completed": False,
                "owner": "human",
            },
            {
                "item": "Approve merge",
                "required": True,
                "completed": False,
                "owner": "human",
            },
            {
                "item": "Approve production deployment separately",
                "required": True,
                "completed": False,
                "owner": "human",
            },
        ],
        "safety": {
            "merges": False,
            "deploys": False,
            "live_trading": False,
            "places_orders": False,
            "changes_risk_limits": False,
            "accesses_secrets": False,
        },
        "requires_human_approval": ["merge", "production deployment", "live trading"],
    }


def load_report(path: Path) -> dict:
    size = path.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError("Verification report is too large.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read verification report: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Verification report must be a JSON object.")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verification_report", type=Path)
    args = parser.parse_args()

    try:
        report = load_report(args.verification_report)
        checklist = build_release_checklist(report)
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(checklist, indent=2, sort_keys=True))
    return 0 if checklist["ready_for_human_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
