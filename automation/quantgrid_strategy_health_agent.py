from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlencode

from common_health import request_json, summarize


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_STRATEGIES = (
    "amd",
    "breakout",
    "btst",
    "cbt",
    "crt_tbs",
    "mean_reversion",
    "mtf",
    "mtfa",
    "supply_demand",
)


def run_checks(
    *,
    base_url: str = DEFAULT_BASE_URL,
    token: str | None = None,
    strategies: tuple[str, ...] = DEFAULT_STRATEGIES,
) -> dict:
    base = base_url.rstrip("/")
    results = [
        request_json("backend_health", f"{base}/health"),
        request_json(
            "nifty_1m_candles",
            f"{base}/market/candles/NIFTY?{urlencode({'interval': '1m'})}",
            token=token,
        ),
    ]

    if token:
        for strategy in strategies:
            results.append(
                request_json(
                    f"signal_{strategy}",
                    f"{base}/trading/signals",
                    method="POST",
                    token=token,
                    payload={
                        "strategy_name": strategy,
                        "symbol": "NIFTY",
                        "capital": 100000,
                        "risk_pct": 1,
                        "rr_ratio": 2,
                        "include_diagnostics": True,
                        "candles": [],
                        "mtf_candles": [],
                        "htf_candles": [],
                        "daily_candles": [],
                    },
                    timeout=20.0,
                )
            )

    summary = summarize(results)
    summary["mode"] = "diagnostic-only"
    summary["signal_checks_skipped"] = token is None
    summary["safety"] = {
        "live_trading": False,
        "places_orders": False,
        "changes_risk_limits": False,
        "restarts_services": False,
        "writes_database": False,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only QuantGrid strategy/backend health agent."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("QUANTGRID_AGENT_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument(
        "--token",
        default=os.getenv("QUANTGRID_AGENT_TOKEN"),
        help="Optional bearer token. Never printed.",
    )
    args = parser.parse_args()

    result = run_checks(base_url=args.base_url, token=args.token)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
