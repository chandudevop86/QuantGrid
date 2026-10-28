#!/usr/bin/env python3
"""Opt-in OFFLINE benchmark of the real QuantGrid backtesting engine.

Uses deterministic synthetic candles, not provider history or live trading.
No DB writes, broker calls or production configuration changes are intended.
Run only on a nonproduction copy / isolated worktree with a test environment.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time


def candles_for(symbol: str, count: int) -> list[dict]:
    from datetime import datetime, timedelta, timezone
    base = 23000.0 if symbol == "NIFTY" else 52000.0
    start = datetime(2026, 9, 1, 3, 45, tzinfo=timezone.utc)
    result = []
    for i in range(count):
        center = base + (i % 97 - 48) * 1.5 + i * 0.02
        close = center + (i % 11 - 5) * 0.4
        result.append({"timestamp": (start + timedelta(minutes=i)).isoformat(),
                       "open": center, "high": max(center, close) + 2,
                       "low": min(center, close) - 2, "close": close,
                       "volume": 10000 + i % 100})
    return result


def child(args: argparse.Namespace) -> None:
    # Periodic Python stack snapshots help locate stalls without changing engine behavior.
    faulthandler.enable(file=sys.stderr)
    faulthandler.dump_traceback_later(8, repeat=True, file=sys.stderr)
    # Disable outbound network before importing any trading application modules.
    import socket
    def forbidden(*_args, **_kwargs):
        raise RuntimeError("network access forbidden during offline benchmark")
    socket.socket.connect = forbidden
    socket.create_connection = forbidden

    service = Path(__file__).resolve().parents[1] / "services" / "trading-service"
    sys.path.insert(0, str(service))
    print("phase=import_start", file=sys.stderr, flush=True)
    from Backend.application.quant_modules import backtesting_module
    print("phase=import_complete", file=sys.stderr, flush=True)

    started = time.monotonic()
    print("phase=calculation_start", file=sys.stderr, flush=True)
    result = backtesting_module({
        "symbol": args.symbol,
        "strategy_name": args.strategy,
        "candles": candles_for(args.symbol, args.candles),
        "max_candles": args.candles,
        "capital": 100000,
    })
    print("phase=calculation_complete", file=sys.stderr, flush=True)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    faulthandler.cancel_dump_traceback_later()
    print(json.dumps({
        "status": "completed", "workload": "real_engine_synthetic_candles",
        "symbol": args.symbol, "strategy": args.strategy, "candles": args.candles,
        "duration_seconds": round(time.monotonic() - started, 4),
        "peak_rss_mib": round(peak, 2),
        "total_trades": result.get("metrics", {}).get("total_trades"),
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--symbol", choices=["NIFTY", "BANKNIFTY"], default="NIFTY")
    parser.add_argument("--strategy", choices=["amd", "breakout", "btst", "cbt", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"], default="breakout")
    parser.add_argument("--candles", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    if not 100 <= args.candles <= 4000 or not 1 <= args.timeout <= 120:
        parser.error("candles must be 100..4000; timeout must be 1..120 seconds")
    if args.child:
        child(args)
        return
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PYTHONDONTWRITEBYTECODE": "1",
           "QUANTGRID_ENV": "test",
           "QUANTGRID_TRADING_MODE": "paper",
           "QUANTGRID_BACKTEST_PROCESS_ISOLATION": "0"}
    command = [sys.executable, "-I", str(Path(__file__).resolve()), "--child",
               "--symbol", args.symbol, "--strategy", args.strategy,
               "--candles", str(args.candles)]
    started = time.monotonic()
    try:
        proc = subprocess.run(command, env=env, text=True, capture_output=True,
                              timeout=args.timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        print(json.dumps({"status": "timeout", "timeout_seconds": args.timeout,
                          "phase_log": stderr[-7000:]}))
        raise SystemExit(1)
    if proc.returncode:
        missing_dependency = "ModuleNotFoundError" in proc.stderr
        print(json.dumps({"status": "dependency_error" if missing_dependency else "failed",
                          "exit_code": proc.returncode,
                          "python_executable": sys.executable,
                          "hint": "Use the existing QuantGrid backend virtualenv Python; do not install into system Python." if missing_dependency else None,
                          "stderr_tail": proc.stderr[-1500:]}))
        raise SystemExit(1)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(json.dumps({"status": "invalid_output", "stdout_tail": proc.stdout[-500:]}))
        raise SystemExit(1)
    data["wall_seconds"] = round(time.monotonic() - started, 4)
    data["child_exit_code"] = proc.returncode
    print(json.dumps(data, sort_keys=True))


if __name__ == "__main__":
    main()
