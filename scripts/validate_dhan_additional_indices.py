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

# Verified against Dhan NSE / I / INDEX instrument master on 2026-10-22.
# IDs remain validation-only: this script does not activate ingestion.
INDEX_SECURITY_IDS = {
    "MIDCPNIFTY": "442",
    "NIFTYNEXT50": "38",
    "NIFTYIT": "29",
    "NIFTYAUTO": "14",
    "NIFTYPHARMA": "32",
    "NIFTYFMCG": "28",
    "NIFTYMETAL": "31",
    "NIFTYREALTY": "34",
}


def main() -> int:
    provider = DhanProvider()
    verified = []
    skipped = []
    failed = []
    for symbol, expected_id in INDEX_SECURITY_IDS.items():
        security_id = os.getenv(f"DHAN_SECURITY_ID_{symbol}", "").strip()
        if not security_id:
            skipped.append(symbol)
            print(f"SKIP {symbol}: DHAN_SECURITY_ID_{symbol} not configured (master ID {expected_id})")
            continue
        if security_id != expected_id:
            failed.append(symbol)
            print(f"FAIL {symbol}: configured ID differs from verified master ID {expected_id}")
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
            for candle in candles:
                o, h, l, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
                if not (l <= o <= h and l <= c <= h and l > 0):
                    raise ValueError("invalid OHLC candle")
            verified.append(symbol)
            print(f"PASS {symbol}: candles={len(candles)} latest={latest['timestamp']}")
        except Exception as exc:
            failed.append(symbol)
            print(f"FAIL {symbol}: {type(exc).__name__}: {exc}")
    print(f"Summary: verified={verified} skipped={skipped} failed={failed}")
    return 1 if failed or skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
