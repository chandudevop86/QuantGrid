"""Safe local verification runner for QuantGrid agents.

Only predefined checks may run. Arbitrary commands, live trading,
deployment, secret access, and direct repository mutation are out of scope.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SAFE_CHECKS = {
    "automation-tests": {
        "argv": [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "automation",
            "-p",
            "test_*.py",
            "-v",
        ],
        "cwd": ROOT,
    },
    "git-diff-check": {
        "argv": ["git", "diff", "--check"],
        "cwd": ROOT,
    },
}


def run_check(name: str, *, execute: bool = False) -> dict:
    if name not in SAFE_CHECKS:
        raise ValueError(f"Unknown or unapproved check: {name}")

    spec = SAFE_CHECKS[name]
    argv = list(spec["argv"])
    cwd = Path(spec["cwd"])

    result = {
        "check": name,
        "argv": argv,
        "cwd": str(cwd),
        "executed": False,
        "returncode": None,
    }

    if not execute:
        return result

    completed = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        shell=False,
    )

    result["executed"] = True
    result["returncode"] = completed.returncode
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=sorted(SAFE_CHECKS))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the selected allow-listed check.",
    )
    args = parser.parse_args()

    result = run_check(args.check, execute=args.execute)
    print(json.dumps(result, indent=2))

    if result["executed"] and result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__ == "__main__":
    main()
