"""Read-only comparison of Dhan and Yahoo NIFTY spot-index 1-minute bars.

Fetches independently from DhanHQ INDEX/IDX_I and Yahoo ^NSEI.
Optionally compares the original PostgreSQL rows to Dhan WITHOUT modifying them.

Example on the trading server (never prints credentials):
 PYTHONPATH=services/trading-service python scripts/compare_nifty_providers.py \
   --start 2026-10-01 --end 2026-10-16 --include-stored \
   --output /tmp/quantgrid-nifty-provider-compare.json

The 1m Yahoo feed normally has short retention; an October 1 Yahoo
cross-check may be unavailable. Missing comparison evidence is NOT a pass.
Dhan and Yahoo are independent data sources, but agreement is not proof
of exchange certification or live-execution fitness.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")
OHLC = ("open", "high", "low", "close")
FIELDS = ("timestamp", *OHLC, "volume")
NIFTY_DHAN_SECURITY_ID = "13"  # Dhan index mapping also used by DhanProvider.get_ltp
MIN_OVERLAP = 30


class ProviderComparisonError(ValueError):
    pass


def classify_dhan_failure(payload: dict[str, Any]) -> str:
    """Return non-sensitive error class; never disclose raw SDK/HTTP payloads."""
    fields = [payload]
    if isinstance(payload.get("data"), dict):
        fields.append(payload["data"])
    codes = [str(p.get(key) or "").upper().strip()
             for p in fields for key in ("errorCode", "error_code", "code")]
    code = next((x for x in codes if x in {
        "DH-901", "DH-902", "DH-903", "DH-904", "DH-905", "DH-907",
        "DH-908", "DH-909", "806", "807", "808", "809", "810",
        "812", "813", "814", "800", "805",
    }), None)
    categories = {
        "DH-901": "AUTHENTICATION", "807": "AUTHENTICATION",
        "808": "AUTHENTICATION", "809": "AUTHENTICATION",
        "810": "AUTHENTICATION", "DH-902": "DATA_API_SUBSCRIPTION",
        "806": "DATA_API_SUBSCRIPTION",
        "DH-904": "RATE_LIMIT", "805": "RATE_LIMIT",
        "DH-905": "INVALID_REQUEST", "812": "INVALID_REQUEST",
        "813": "INVALID_REQUEST", "814": "INVALID_REQUEST",
        "DH-907": "NO_DATA_OR_PARAMETERS", "DH-908": "SERVER_ERROR",
        "DH-909": "NETWORK_ERROR", "800": "SERVER_ERROR",
    }
    if code:
        return f"{categories.get(code, 'DHAN_FAILURE')} ({code})"
    # Recognize a previously reported DhanHQ SDK JSON-decoding issue.
    # Do not include the original message; it can contain identifiers.
    messages = " ".join(
        str(p.get(key) or "") for p in fields
        for key in ("remarks", "errorMessage", "message", "errorType")
    ).lower()
    if ("expecting value" in messages or "extra data: line" in messages
            or "jsondecodeerror" in messages):
        return "SDK_RESPONSE_JSON_PARSE_FAILURE"
    if "not subscribed" in messages or "subscription" in messages:
        return "DATA_API_SUBSCRIPTION"
    if "token" in messages or "unauthoriz" in messages:
        return "AUTHENTICATION"
    if "rate limit" in messages or "too many requests" in messages:
        return "RATE_LIMIT"
    if "no data" in messages:
        return "NO_DATA_OR_PARAMETERS"
    return "UNKNOWN_DHAN_PROVIDER_FAILURE"


def utc_window(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ProviderComparisonError("End date must not precede start date.")
    left = pd.Timestamp(datetime.combine(first, time.min, IST)).tz_convert("UTC")
    right = pd.Timestamp(datetime.combine(last + timedelta(days=1), time.min, IST)).tz_convert("UTC")
    return left, right


def fetch_dhan(start: str, end: str, *, security_id: str | None = None) -> pd.DataFrame:
    """Market-data SDK only. No orders, token printing, writes or trading."""
    from Backend.core.config import ensure_env_loaded
    from Backend.infrastructure.market_data.dhan_sdk import dhan_sdk_client
    from Backend.infrastructure.market_data.dhan_provider import _normalize_candles

    # Respect QuantGrid's existing secure environment-file policy.
    ensure_env_loaded()
    security_id = security_id or os.getenv("DHAN_SECURITY_ID_NIFTY") or NIFTY_DHAN_SECURITY_ID
    if not str(security_id).isdigit():
        raise ProviderComparisonError("Dhan NIFTY index security ID must be numeric.")
    sdk = dhan_sdk_client()
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if (last - first).days >= 90:
        raise ProviderComparisonError("Dhan intraday query must cover fewer than 90 calendar days.")
    # Never request future API history when the requested end is today.
    end_requested = datetime.combine(last + timedelta(days=1), time.min, IST)
    end_available = min(end_requested, datetime.now(IST))
    if end_available <= datetime.combine(first, time(9, 15), IST):
        raise ProviderComparisonError("Requested Dhan interval is entirely in the future.")
    raw = sdk.intraday_minute_data(
        security_id=str(security_id),
        exchange_segment="IDX_I",
        instrument_type="INDEX",
        from_date=f"{first.isoformat()} 09:15:00",
        to_date=end_available.strftime("%Y-%m-%d %H:%M:%S"),
        interval=1,
        oi=False,
    )
    if not isinstance(raw, dict):
        raise ProviderComparisonError("Unexpected Dhan SDK response type.")
    if str(raw.get("status", "")).lower() in {"failed", "error", "failure"}:
        category = classify_dhan_failure(raw)
        raise ProviderComparisonError(f"Dhan request rejected: {category}")
    candles = _normalize_candles("NIFTY", raw)
    return pd.DataFrame(candles)


def fetch_yahoo() -> pd.DataFrame:
    """Untruncated Yahoo 7d chart; YahooProvider.get_candles caps at 500 bars."""
    from Backend.infrastructure.market_data.yahoo_provider import YahooProvider

    chart = YahooProvider().fetch_chart("NIFTY", interval="1m", period="7d")
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    timestamps = chart.get("timestamp") or []
    rows = []
    for i, value in enumerate(timestamps):
        try:
            prices = [float(quote[field][i]) for field in OHLC]
            if not all(pd.notna(x) for x in prices):
                continue
            candle_time = datetime.fromtimestamp(int(value), UTC)
            volume = (quote.get("volume") or [])
            rows.append({
                "timestamp": candle_time.isoformat(),
                **dict(zip(OHLC, prices)),
                "volume": volume[i] if i < len(volume) and volume[i] is not None else 0,
            })
        except (IndexError, ValueError, TypeError, KeyError):
            continue
    return pd.DataFrame(rows)


def fetch_stored(start: str, end: str) -> pd.DataFrame:
    from sqlalchemy import text
    from Backend.core.database import SessionLocal
    low, high = utc_window(start, end)
    with SessionLocal() as db:
        result = db.execute(text(
            "SELECT timestamp, open, high, low, close, volume, source "
            "FROM market_candles WHERE symbol = 'NIFTY' AND interval = '1m' "
            "AND timestamp >= :start AND timestamp < :end ORDER BY timestamp"
        ), {"start": low.to_pydatetime(), "end": high.to_pydatetime()})
        return pd.DataFrame(
            result.fetchall(), columns=[*FIELDS, "source"]
        )


def audit_bars(frame: pd.DataFrame, *, label: str, start: str, end: str,
               now: pd.Timestamp | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Filter only for *comparison*, preserving original unfiltered data."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=FIELDS), {
            "provider": label, "total_returned": 0, "eligible_bars": 0,
            "reason": "provider returned no bars",
        }
    if not set(FIELDS).issubset(set(frame.columns)):
        raise ProviderComparisonError(f"{label}: returned data missing required OHLCV columns.")

    copy = frame.copy()
    try:
        copy["timestamp"] = pd.to_datetime(copy["timestamp"], utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ProviderComparisonError(f"{label}: invalid timestamps.") from exc
    for key in [*OHLC, "volume"]:
        copy[key] = pd.to_numeric(copy[key], errors="coerce")

    left, right = utc_window(start, end)
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    local = copy["timestamp"].dt.tz_convert(IST)
    minute = local.dt.hour * 60 + local.dt.minute
    within_session = (
        (local.dt.dayofweek < 5) & (minute >= 555) & (minute < 930)
    )
    aligned = (local.dt.second == 0) & (local.dt.microsecond == 0)
    ohlc_valid = (
        copy[list(OHLC)].notna().all(axis=1) &
        (copy["low"] > 0) & (copy["high"] >= copy["low"]) &
        (copy["high"] >= copy[["open", "close"]].max(axis=1)) &
        (copy["low"] <= copy[["open", "close"]].min(axis=1))
    )
    in_requested_dates = (copy["timestamp"] >= left) & (copy["timestamp"] < right)
    candle_completed = (copy["timestamp"] + pd.Timedelta(minutes=1) <= now)
    valid = within_session & aligned & ohlc_valid & in_requested_dates & candle_completed

    accepted = copy.loc[valid].copy()
    duplicate_timestamp_count = int(accepted["timestamp"].duplicated(keep=False).sum())
    accepted = accepted.loc[~accepted["timestamp"].duplicated(keep=False)].copy()
    accepted = accepted.sort_values("timestamp").reset_index(drop=True)

    days = {}
    if not accepted.empty:
        local_times = accepted["timestamp"].dt.tz_convert(IST)
        for day, group in accepted.groupby(local_times.dt.date):
            observed = set(group["timestamp"].dt.tz_convert(IST).dt.strftime("%H:%M"))
            expected = set(pd.date_range(
                f"{day} 09:15", periods=375, freq="min", tz=IST,
            ).strftime("%H:%M"))
            missing = sorted(expected - observed)
            days[str(day)] = {
                "valid_minutes": len(observed),
                "missing_minutes": len(missing),
                "missing_sample": missing[:20],
            }

    profile: dict[str, Any] = {
        "provider": label,
        "total_returned": len(copy),
        "eligible_bars": len(accepted),
        "out_of_session": int((~within_session).sum()),
        "offset_second_rows": int((~aligned).sum()),
        "bad_ohlc": int((~ohlc_valid).sum()),
        "out_of_date_range": int((~in_requested_dates).sum()),
        "unfinished_candles": int((~candle_completed).sum()),
        "duplicate_timestamp_rows_excluded": duplicate_timestamp_count,
        "first_utc": accepted["timestamp"].iloc[0].isoformat() if not accepted.empty else None,
        "last_utc": accepted["timestamp"].iloc[-1].isoformat() if not accepted.empty else None,
        "days": days,
    }
    if "source" in copy.columns:
        profile["original_source_labels"] = {
            str(k): int(v) for k, v in copy["source"].fillna("<missing>").value_counts().items()
        }
    return accepted, profile


def compare_bars(primary: pd.DataFrame, comparison: pd.DataFrame, *,
                 label: str, tolerance: float = 1.0) -> dict[str, Any]:
    if primary.empty or comparison.empty:
        return {"pair": label, "result": "INSUFFICIENT_OVERLAP", "matched_minutes": 0}
    joined = primary.merge(comparison, on="timestamp", how="inner", suffixes=("_dhan", "_reference"))
    if joined.empty:
        return {"pair": label, "result": "INSUFFICIENT_OVERLAP", "matched_minutes": 0}
    # BOS, CHoCH and FVG also depend on high/low/open: close-only agreement
    # is insufficient to validate smart-money structure.
    field_errors = {
        field: (joined[f"{field}_dhan"] - joined[f"{field}_reference"]).abs()
        for field in OHLC
    }
    close_error = field_errors["close"]
    max_error = float(close_error.max())
    mismatch = close_error > tolerance
    max_ohlc_error = pd.DataFrame(field_errors).max(axis=1)
    any_ohlc_mismatch = max_ohlc_error > tolerance
    worst = joined.assign(close_difference=close_error).sort_values("close_difference", ascending=False).head(12)
    result = (
        "INSUFFICIENT_OVERLAP" if len(joined) < MIN_OVERLAP
        else "DISAGREEMENT" if any_ohlc_mismatch.any()
        else "OHLC_AGREEMENT"
    )
    date_labels = joined["timestamp"].dt.tz_convert(IST).dt.strftime("%Y-%m-%d")
    per_day = {
        str(day): {
            "matched_minutes": int(len(group)),
            "different_close_count": int((group["close_dhan"] - group["close_reference"]).abs().gt(tolerance).sum()),
            "different_ohlc_count": int(pd.DataFrame({
                field: (group[f"{field}_dhan"] - group[f"{field}_reference"]).abs()
                for field in OHLC
            }).max(axis=1).gt(tolerance).sum()),
            "max_close_difference_points": round(
                float((group["close_dhan"] - group["close_reference"]).abs().max()), 4
            ),
        }
        for day, group in joined.groupby(date_labels)
    }
    return {
        "pair": label,
        "result": result,
        "matched_minutes": len(joined),
        "dhan_minutes_not_in_reference": len(primary) - len(joined),
        "reference_minutes_not_in_dhan": len(comparison) - len(joined),
        "close_price_tolerance_points": float(tolerance),
        "different_close_count": int(mismatch.sum()),
        "different_ohlc_count": int(any_ohlc_mismatch.sum()),
        "max_abs_difference_by_ohlc_field": {
            field: round(float(values.max()), 4) for field, values in field_errors.items()
        },
        "mean_abs_close_difference_points": round(float(close_error.mean()), 4),
        "maximum_abs_close_difference_points": round(max_error, 4),
        "per_ist_date": per_day,
        "worst_close_differences": [
            {
                "timestamp_utc": row["timestamp"].isoformat(),
                "dhan": round(float(row["close_dhan"]), 4),
                "reference": round(float(row["close_reference"]), 4),
                "difference_points": round(float(row["close_difference"]), 4),
            }
            for _, row in worst.iterrows()
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="First IST date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Last IST date, YYYY-MM-DD")
    parser.add_argument("--include-stored", action="store_true", help="Compare original DB data; SELECT only")
    parser.add_argument("--dhan-security-id", help="NIFTY spot-index security ID; default 13 or DHAN_SECURITY_ID_NIFTY")
    parser.add_argument("--tolerance-points", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("/tmp/quantgrid-nifty-provider-compare.json"))
    args = parser.parse_args()
    if args.tolerance_points < 0:
        parser.error("Tolerance must be nonnegative.")
    try:
        utc_window(args.start, args.end)
        dhan_error = None
        try:
            dhan_raw = fetch_dhan(args.start, args.end, security_id=args.dhan_security_id)
        except Exception as exc:
            # Never print raw SDK errors: some SDKs include request metadata.
            dhan_error = (
                str(exc) if isinstance(exc, ProviderComparisonError)
                else f"Dhan SDK/transport error ({type(exc).__name__})"
            )
            dhan_raw = pd.DataFrame()
        yahoo_error = None
        try:
            yahoo_raw = fetch_yahoo()
        except Exception as exc:
            yahoo_error = f"Yahoo request unavailable ({type(exc).__name__})."
            yahoo_raw = pd.DataFrame()
        dhan, dhan_profile = audit_bars(dhan_raw, label="dhan", start=args.start, end=args.end)
        yahoo, yahoo_profile = audit_bars(yahoo_raw, label="yahoo", start=args.start, end=args.end)
        comparisons = [compare_bars(dhan, yahoo, label="dhan_vs_yahoo",
                                    tolerance=args.tolerance_points)]
        profiles = {"dhan": dhan_profile, "yahoo": yahoo_profile}
        if args.include_stored:
            stored, stored_profile = audit_bars(
                fetch_stored(args.start, args.end), label="stored_postgres",
                start=args.start, end=args.end,
            )
            profiles["stored_postgres"] = stored_profile
            comparisons.append(compare_bars(
                dhan, stored, label="dhan_vs_existing_postgres",
                tolerance=args.tolerance_points,
            ))
        # If Dhan fails, still report Yahoo/stored coverage but NEVER certify
        # consistency or turn the comparison into a successful validation.
        report = {
            "status": (
                "PARTIAL_DHAN_UNAVAILABLE_NO_VALIDATION"
                if dhan.empty else "RESEARCH_ONLY_NO_LIVE_OR_PROFIT_APPROVAL"
            ),
            "symbol": "NIFTY_SPOT",
            "date_range_ist": [args.start, args.end],
            "provider_profiles": profiles,
            "comparisons": comparisons,
            "warnings": [
                "Dhan IDX_I index candles compared with Yahoo ^NSEI (paper-only comparison).",
                "Yahoo 1m retrieval uses the last 7 days and may not cover October 1.",
                "No database writes, order placement, automatic repair or provider relabeling.",
                "Source agreement and data completeness do not establish trading profitability.",
            ],
        }
        if yahoo_error:
            report["warnings"].append(yahoo_error)
        if dhan_error:
            report["dhan_error_category"] = dhan_error
            report["warnings"].append(
                "Dhan unavailable: Yahoo and stored data are descriptive only; "
                "no cross-provider validation was performed."
            )
    except ProviderComparisonError as exc:
        parser.exit(2, f"COMPARISON NOT COMPLETED: {exc}\n")
    except Exception as exc:
        # Provider SDK failures must not print credentials or raw responses.
        parser.exit(2, f"COMPARISON NOT COMPLETED: provider/db error ({type(exc).__name__}).\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "dhan_eligible": profiles["dhan"]["eligible_bars"],
        "yahoo_eligible": profiles["yahoo"]["eligible_bars"],
        "comparisons": comparisons,
        "report_path": str(args.output),
    }, indent=2))
    return 2 if dhan.empty else 0


if __name__ == "__main__":
    raise SystemExit(main())
