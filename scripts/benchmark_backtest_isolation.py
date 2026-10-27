#!/usr/bin/env python3
"""Offline synthetic candle benchmark. NOT a real-strategy benchmark or trading signal.

No application imports, broker credentials, database access, or network calls.
Run on a quiet host: python scripts/benchmark_backtest_isolation.py
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time


def synthetic_calculation(candles: int, rounds: int) -> dict:
    # Deterministic, bounded CPU workload with candle-like OHLC data.
    prices = [22000.0 + (i % 101) * 0.25 for i in range(candles)]
    closes = [p + ((i % 7) - 3) * 0.15 for i, p in enumerate(prices)]
    signal_count = 0
    for _ in range(rounds):
        for i in range(20, candles):
            mean = sum(closes[i - 20:i]) / 20
            signal_count += closes[i] > mean
    return {"candles": candles, "rounds": rounds, "synthetic_signals": signal_count}


def run_child(args: argparse.Namespace) -> None:
    started = time.monotonic()
    result = synthetic_calculation(args.candles, args.rounds)
    rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({
        "workload": "synthetic_only",
        "duration_seconds": round(time.monotonic() - started, 4),
        "peak_rss_mib": round(rss_kib / 1024, 2),
        "result": result,
    }))


def run_parent(args: argparse.Namespace) -> None:
    if args.candles < 50 or args.candles > 100000 or args.rounds < 1 or args.rounds > 100:
        raise SystemExit("candles must be 50..100000 and rounds must be 1..100")
    if args.timeout < 1 or args.timeout > 300:
        raise SystemExit("timeout must be 1..300 seconds")
    # Avoid forwarding tokens and service configuration to benchmark subprocess.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "PYTHONIOENCODING")
           if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, "-I", os.path.abspath(__file__), "--child",
           "--candles", str(args.candles), "--rounds", str(args.rounds)]
    before = available_mib()
    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                   timeout=args.timeout, check=False)
    except subprocess.TimeoutExpired:
        print(json.dumps({"status": "timeout", "timeout_seconds": args.timeout,
                          "workload": "synthetic_only"}))
        raise SystemExit(1)
    output = {
        "status": "completed" if completed.returncode == 0 else "failed",
        "workload": "synthetic_only",
        "wall_seconds": round(time.monotonic() - started, 4),
        "memory_available_before_mib": before,
        "memory_available_after_mib": available_mib(),
        "child_exit_code": completed.returncode,
    }
    if completed.returncode == 0:
        try:
            output.update(json.loads(completed.stdout))
        except json.JSONDecodeError:
            output["status"] = "invalid_child_output"
    else:
        output["child_stderr_tail"] = completed.stderr[-1000:]
    print(json.dumps(output, sort_keys=True))
    if output["status"] != "completed":
        raise SystemExit(1)


def available_mib() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--candles", type=int, default=2000)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.child:
        run_child(args)
    else:
        run_parent(args)


if __name__ == "__main__":
    main()
