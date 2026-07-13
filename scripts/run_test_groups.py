from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _test_files(pattern: str) -> list[Path]:
    return sorted((ROOT / "tests").glob(pattern))


def _groups(files: list[Path], count: int) -> list[list[Path]]:
    count = max(1, min(count, len(files) or 1))
    size = math.ceil(len(files) / count)
    return [files[index : index + size] for index in range(0, len(files), size)]


def _run(command: list[str], timeout: int, *, verbose: bool = False) -> None:
    print("+", " ".join(command), flush=True)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            timeout=timeout,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            output = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
            print(output, end="" if output.endswith("\n") else "\n")
        print(f"Test group timed out after {timeout}s: {' '.join(command)}", file=sys.stderr)
        raise SystemExit(124) from exc
    if result.stdout and (verbose or result.returncode != 0):
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QuantGrid pytest files in deterministic groups.")
    parser.add_argument("--groups", type=int, default=4, help="Number of pytest groups to run.")
    parser.add_argument("--group-timeout", type=int, default=180, help="Timeout per group in seconds.")
    parser.add_argument("--test-timeout", type=int, default=60, help="Timeout per pytest test in seconds.")
    parser.add_argument("--pattern", default="test_*.py", help="Test file glob under tests/.")
    parser.add_argument("--coverage", action="store_true", help="Collect combined coverage across groups.")
    parser.add_argument("--cov-fail-under", type=int, default=45, help="Coverage threshold for --coverage.")
    parser.add_argument("--verbose", action="store_true", help="Print stdout for passing pytest groups.")
    args = parser.parse_args()

    files = _test_files(args.pattern)
    if not files:
        raise SystemExit("No tests found.")

    coverage_file = ROOT / ".coverage"
    if args.coverage and coverage_file.exists():
        coverage_file.unlink()

    for index, group in enumerate(_groups(files, args.groups), start=1):
        print(f"Running pytest group {index}: {len(group)} files", flush=True)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"--timeout={args.test_timeout}",
            "--timeout-method=thread",
            *[str(path.relative_to(ROOT)) for path in group],
        ]
        if args.coverage:
            command.extend(["--cov=services/trading-service/Backend", "--cov-append", "--cov-report="])
        _run(command, timeout=args.group_timeout, verbose=args.verbose)
        print(f"Pytest group {index} passed.", flush=True)

    if args.coverage:
        _run(
            [sys.executable, "-m", "coverage", "report", "--fail-under", str(args.cov_fail_under)],
            timeout=60,
            verbose=True,
        )


if __name__ == "__main__":
    main()
