"""Read-only Dhan 1-minute candle validation for additional NSE indices.

Run from services/trading-service with the venv Python after loading .env.
Never submits orders or writes candles.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

TRADING_SERVICE = Path(__file__).resolve().parents[1] / "services" / "trading-service"
sys.path.insert(0, str(TRADING_SERVICE))

from Backend.infrastructure.market_data.dhan_provider import DhanProvider

INDEX_CANDIDATES = (
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNEXT50",
    "NIFTYIT",
    "NIFTYAUTO",
    "NIFTYPHARMA",
    "NIFTYFMCG",
    "NIFTYMETAL",
    "NIFTYREALTY",
)


def main() -> int:
    provider = DhanProvider()
    verified = []
    skipped = []
    failed = []
    for symbol in INDEX_CANDIDATES:
        security_id = os.getenv(f"DHAN_SECURITY_ID_{symbol}", "").strip()
        if not security_id:
            skipped.append(symbol)
            print(f"SKIP {symbol}: DHAN_SECURITY_ID_{symbol} not configured")
            continue
        if not security_id.isdecimal():
            failed.append(symbol)
            print(f"FAIL {symbol}: invalid numeric security ID")
            continue
        try:
            candles = provider.get_candles(symbol, "1m", "1d", 5)
            if not candles:
                raise ValueError("Dhan returned no candles")
            latest = candles[-1]
            if str(latest.get("symbol", "")).upper() != symbol:
                raise ValueError("candle symbol mismatch")
            verified.append(symbol)
            print(f"PASS {symbol}: candles={len(candles)} latest={latest['timestamp']}")
        except Exception as exc:
            failed.append(symbol)
            print(f"FAIL {symbol}: {type(exc).__name__}: {exc}")
    print(f"Summary: verified={verified} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
