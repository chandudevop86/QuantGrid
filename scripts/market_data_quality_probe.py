from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get_json(base_url: str, path: str, token: str | None, query: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _sample(base_url: str, token: str | None, symbol: str, interval: str) -> dict[str, Any]:
    health = _get_json(base_url, "/market/provider/status", token, {"symbol": symbol, "interval": interval})
    candles = _get_json(base_url, f"/market/candles/{symbol}", token, {"interval": interval, "period": "1d", "limit": 20})
    validation = candles.get("validation") or {}
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "provider": health.get("provider"),
        "feed_status": health.get("feed_status"),
        "fresh": bool(health.get("fresh")),
        "live_suitable": bool(health.get("live_suitable")),
        "latest_fetch_at": health.get("latest_fetch_at"),
        "feed_delay_seconds": health.get("feed_delay_seconds"),
        "candle_count": len(candles.get("candles") or []),
        "candle_source": candles.get("source"),
        "valid_for_analysis": bool(validation.get("valid_for_analysis")),
        "valid_for_execution": bool(validation.get("valid_for_execution")),
        "market_status": validation.get("market_status"),
    }


def _passes(sample: dict[str, Any], *, require_execution: bool) -> bool:
    if not sample["fresh"] or not sample["live_suitable"]:
        return False
    if not sample["valid_for_analysis"]:
        return False
    if require_execution and not sample["valid_for_execution"]:
        return False
    return int(sample.get("candle_count") or 0) >= 5


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe QuantGrid live market data quality over repeated samples.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=None)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=5.0)
    parser.add_argument("--require-execution", action="store_true")
    args = parser.parse_args()

    samples: list[dict[str, Any]] = []
    for index in range(max(1, args.samples)):
        try:
            samples.append(_sample(args.base_url, args.token, args.symbol, args.interval))
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            samples.append({"timestamp": datetime.utcnow().isoformat(), "error": str(exc)})
        if index < args.samples - 1:
            time.sleep(max(0.0, args.sleep_seconds))

    passed = all(_passes(sample, require_execution=args.require_execution) for sample in samples)
    print(json.dumps({"passed": passed, "samples": samples}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
