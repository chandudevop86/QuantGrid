"""Read-only verification coordinator for QuantGrid agent changes.

This module runs only checks already allow-listed by agent_runner and
returns a structured report. It cannot execute arbitrary commands, deploy,
change risk settings, access credentials, or submit orders.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable

from agent_runner import SAFE_CHECKS, run_check

DEFAULT_CHECKS = ("automation-tests", "git-diff-check")


def verify(
    checks: Iterable[str] = DEFAULT_CHECKS,
    *,
    execute: bool = False,
) -> dict:
    selected = tuple(checks)
    if not selected:
        raise ValueError("At least one verification check is required.")

    unknown = [name for name in selected if name not in SAFE_CHECKS]
    if unknown:
        raise ValueError(
            "Unknown or unapproved verification check(s): " + ", ".join(unknown)
        )

    results = [run_check(name, execute=execute) for name in selected]
    failed = [
        result["check"]
        for result in results
        if result["executed"] and result["returncode"] not in (0, None)
    ]

    return {
        "mode": "verification-only",
        "executed": execute,
        "healthy": not failed,
        "checks": results,
        "failed_checks": failed,
        "safety": {
            "arbitrary_commands": False,
            "live_trading": False,
            "places_orders": False,
            "changes_risk_limits": False,
            "deploys": False,
            "accesses_secrets": False,
        },
        "requires_human_approval": ["merge", "production deployment", "live trading"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checks",
        nargs="*",
        default=list(DEFAULT_CHECKS),
        help="Allow-listed verification checks to run.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the checks instead of returning a dry-run plan.",
    )
    args = parser.parse_args()

    report = verify(args.checks, execute=args.execute)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
