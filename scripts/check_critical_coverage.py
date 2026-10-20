from __future__ import annotations

import argparse
from pathlib import Path

from coverage import Coverage

ROOT = Path(__file__).resolve().parents[1]

CRITICAL_MODULES = [
    ROOT / "services/trading-service/Backend/application/broker_reconciliation.py",
    ROOT / "services/trading-service/Backend/application/execution/execution_guardrails.py",
    ROOT / "services/trading-service/Backend/application/risk_gate.py",
    ROOT / "services/trading-service/Backend/application/trade_exit_engine.py",
]


def _statement_coverage(cov: Coverage, path: Path) -> tuple[int, int, float]:
    _filename, statements, _excluded, missing, _missing_formatted = cov.analysis2(str(path))
    total = len(statements)
    covered = total - len(missing)
    pct = 100.0 if total == 0 else (covered / total) * 100.0
    return covered, total, pct


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce per-file coverage for risk-critical QuantGrid modules.")
    parser.add_argument("--fail-under", type=float, default=80.0)
    args = parser.parse_args()

    cov = Coverage(data_file=str(ROOT / ".coverage"))
    cov.load()

    failed = False
    for path in CRITICAL_MODULES:
        covered, total, pct = _statement_coverage(cov, path)
        rel = path.relative_to(ROOT).as_posix()
        print(f"{rel}: {covered}/{total} statements = {pct:.1f}%")
        if pct + 1e-9 < args.fail_under:
            failed = True
            print(f"ERROR: {rel} is below {args.fail_under:.1f}%")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
