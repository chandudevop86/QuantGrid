from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _service_root() -> Path:
    return Path(__file__).resolve().parents[1] / "services" / "trading-service"


def _evaluator():
    sys.path.insert(0, str(_service_root()))
    from Backend.application.real_money_readiness import evaluate_real_money_evidence

    return evaluate_real_money_evidence


def _load_repository_trades() -> list[dict[str, Any]]:
    sys.path.insert(0, str(_service_root()))

    from Backend.application.paper_trade_store import list_trade_journal

    return list_trade_journal(limit=500)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed real-money readiness evidence check for QuantGrid paper trading."
    )
    parser.add_argument("--min-sessions", type=int, default=30)
    parser.add_argument(
        "--json-file",
        default=None,
        help="Optional JSON file containing a list of trade records. Defaults to the configured trade journal.",
    )
    args = parser.parse_args()

    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("--json-file must contain a JSON list of trade records")
        trades = payload
    else:
        trades = _load_repository_trades()

    result = _evaluator()(trades, min_sessions=max(1, args.min_sessions))
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
