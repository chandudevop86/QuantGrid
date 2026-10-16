"""Read-only, candle-close-safe NIFTY SMC replay audit.

This tool audits signal timing and market structure. It does NOT simulate
option premiums, place orders, or claim trading profitability.

Example (server with existing market_candles data):
 PYTHONPATH=services/trading-service python scripts/replay_nifty_smc.py \
   --from-db --start 2026-10-01 --end 2026-10-16 \
   --assume-naive-timezone UTC --timestamp-role open \
   --output /tmp/nifty-smc-audit.json

Example (5-minute CSV with tz-aware ISO timestamps):
 PYTHONPATH=services/trading-service python scripts/replay_nifty_smc.py \
   --csv /tmp/NIFTY_5m_with_source.csv --source-minutes 5 \
   --timestamp-role open --output /tmp/nifty-smc-audit.json
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.strategies.mtfa.trend_analyzer import TrendAnalyzer
from Backend.domain.strategies.mtfa.trigger_detector import TriggerDetector
from Backend.domain.strategies.mtfa.zone_detector import ZoneDetector

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN_MINUTE = 9 * 60 + 15
SESSION_CLOSE_MINUTE = 15 * 60 + 30
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
SOURCE_COLUMNS = [*COLUMNS, "source"]
# A provider label is not independent proof of market-data authenticity.
ACCEPTED_PROVIDER_LABELS = frozenset({
    "yahoo", "yfinance", "dhan", "nse", "nseindia",
    "fyers", "zerodha", "upstox", "angelone",
})


class ReplayDataError(ValueError):
    """The dataset cannot support a trustworthy closed-candle replay."""


def validate_market_provenance(source: pd.DataFrame) -> dict[str, int]:
    """Reject synthetic, demo, missing and unrecognized provider labels.

    Unit tests may still use generated fixtures directly with normalize_candles.
    A recognized label does not independently certify price authenticity.
    """
    frame = source.copy()
    frame.columns = [str(col).strip().lower() for col in frame.columns]
    if "source" not in frame.columns:
        raise ReplayDataError(
            "Missing source column. Export timestamp, OHLCV AND source; "
            "cannot verify market-data provenance."
        )
    if frame.empty:
        raise ReplayDataError("No candles available for source validation.")
    labels = frame["source"].fillna("").astype(str).str.strip().str.lower()
    counts = {str(label): int(count) for label, count in labels.value_counts().items()}
    rejected = sorted(set(labels) - ACCEPTED_PROVIDER_LABELS)
    if rejected:
        raise ReplayDataError(
            "Unverified or demo market-data source(s) rejected: "
            + ", ".join(repr(label or "<missing>") for label in rejected)
            + ". Use documented real-provider candles; never relabel demo rows."
        )
    return counts


def normalize_candles(
    source: pd.DataFrame, *, source_minutes: int, timestamp_role: str,
    assume_naive_timezone: str | None = None,
) -> pd.DataFrame:
    if source_minutes not in (1, 5):
        raise ReplayDataError("Only 1-minute or 5-minute sources are supported.")
    if timestamp_role not in ("open", "close"):
        raise ReplayDataError("Specify whether the supplied timestamps mark bar open or close.")
    frame = source.copy()
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    for alias in ("datetime", "date", "time"):
        if alias in frame and "timestamp" not in frame:
            frame = frame.rename(columns={alias: "timestamp"})
    if "volume" not in frame:
        frame["volume"] = 0.0  # index quotes often have no actual volume
    missing = sorted(set(COLUMNS) - set(frame.columns))
    if missing:
        raise ReplayDataError(f"Missing OHLC fields: {missing}")
    if frame.empty:
        raise ReplayDataError("No candles were found; historical replay not executed.")

    try:
        dt = pd.to_datetime(frame["timestamp"], errors="raise")
        if not isinstance(dt.dtype, pd.DatetimeTZDtype):
            if not assume_naive_timezone:
                raise ReplayDataError(
                    "Naive timestamps require --assume-naive-timezone (e.g. UTC or Asia/Kolkata)."
                )
            dt = dt.dt.tz_localize(ZoneInfo(assume_naive_timezone), ambiguous="raise", nonexistent="raise")
        frame["timestamp"] = dt.dt.tz_convert("UTC")
    except ReplayDataError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise ReplayDataError(f"Invalid or mixed timestamps: {exc}") from exc

    if timestamp_role == "close":
        frame["timestamp"] -= pd.Timedelta(minutes=source_minutes)

    if frame["timestamp"].duplicated().any():
        raise ReplayDataError("Duplicate candle timestamps must be resolved at the source.")
    for col in COLUMNS[1:]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[["open", "high", "low", "close"]].isna().any().any():
        raise ReplayDataError("At least one OHLC value is missing or not numeric.")
    # NSE cash index candles may not include true exchange volume. Zero is an
    # explicit unavailable-volume sentinel, never affirmative volume evidence.
    frame["volume"] = frame["volume"].fillna(0.0)
    if not (
        (frame["open"] > 0) & (frame["close"] > 0) &
        (frame["low"] > 0) & (frame["high"] >= frame["low"]) &
        (frame["high"] >= frame[["open", "close"]].max(axis=1)) &
        (frame["low"] <= frame[["open", "close"]].min(axis=1)) &
        (frame["volume"] >= 0)
    ).all():
        raise ReplayDataError("Impossible or non-positive OHLC values detected.")

    frame = frame[COLUMNS].sort_values("timestamp").reset_index(drop=True)
    local = frame["timestamp"].dt.tz_convert(IST)
    within_session = local.dt.date.eq(local.dt.date.shift(1))
    gaps = within_session & frame["timestamp"].diff().ne(pd.Timedelta(minutes=source_minutes))
    if gaps.any():
        raise ReplayDataError("Missing or irregular intraday candle intervals; no interpolation allowed.")
    minute = local.dt.hour * 60 + local.dt.minute
    offset = minute - SESSION_OPEN_MINUTE
    valid = (
        (local.dt.dayofweek < 5) & (offset >= 0) &
        (minute + source_minutes <= SESSION_CLOSE_MINUTE) &
        (offset % source_minutes == 0) &
        (local.dt.second == 0) & (local.dt.microsecond == 0)
    )
    if not valid.all():
        sample = local.loc[~valid].iloc[0].isoformat()
        raise ReplayDataError(f"Bar outside aligned NSE regular session: {sample}")
    return frame


def resample_complete(frame: pd.DataFrame, *, source_minutes: int, target_minutes: int) -> pd.DataFrame:
    """Aggregate complete, contiguous bars within each NSE day (09:15 IST anchor)."""
    if target_minutes % source_minutes:
        raise ReplayDataError("Target timeframe must be divisible by source timeframe.")
    if frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    local = frame["timestamp"].dt.tz_convert(IST)
    offset = local.dt.hour * 60 + local.dt.minute - SESSION_OPEN_MINUTE
    group_keys = list(zip(local.dt.date, offset // target_minutes))
    expected = target_minutes // source_minutes
    grouped: dict[tuple[date, int], list[int]] = {}
    for idx, key in enumerate(group_keys):
        grouped.setdefault(key, []).append(idx)
    rows = []
    for (_day, _slot), indices in sorted(grouped.items()):
        group = frame.iloc[indices]
        if len(group) != expected:
            continue
        actual = group["timestamp"].sort_values().reset_index(drop=True)
        start = actual.iloc[0]
        contiguous = all(
            actual.iloc[k] == start + pd.Timedelta(minutes=k * source_minutes)
            for k in range(expected)
        )
        minute_local = start.tz_convert(IST)
        aligned = (
            (minute_local.hour * 60 + minute_local.minute - SESSION_OPEN_MINUTE) % target_minutes == 0
        )
        if not contiguous or not aligned:
            continue
        rows.append({
            "timestamp": start,
            "open": float(group["open"].iloc[0]),
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group["close"].iloc[-1]),
            "volume": float(group["volume"].sum()),
        })
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(rows, columns=COLUMNS)


def load_db_candles(start: str, end: str) -> pd.DataFrame:
    """SELECT only, via QuantGrid's existing trading-service DB configuration."""
    from sqlalchemy import text
    from Backend.core.database import SessionLocal

    start_ist = datetime.combine(date.fromisoformat(start), datetime.min.time(), tzinfo=IST)
    end_ist = datetime.combine(date.fromisoformat(end) + timedelta(days=1), datetime.min.time(), tzinfo=IST)
    if end_ist <= start_ist:
        raise ReplayDataError("End date must not precede start date.")
    session = SessionLocal()
    try:
        result = session.execute(text(
            "SELECT timestamp, open, high, low, close, volume, source FROM market_candles "
            "WHERE symbol = :symbol AND interval IN ('1', '1m') "
            "AND timestamp >= :start AND timestamp < :end "
            "ORDER BY timestamp ASC"
        ), {"symbol": "NIFTY", "start": start_ist, "end": end_ist})
        return pd.DataFrame(result.fetchall(), columns=SOURCE_COLUMNS)
    finally:
        session.close()


def replay(frame_5m: pd.DataFrame) -> list[dict]:
    """Use freshly computed prefixes; no indicator or trend sees future candles."""
    frame_15m = resample_complete(frame_5m, source_minutes=5, target_minutes=15)
    indicator = IndicatorService()
    trend = TrendAnalyzer()
    trigger = TriggerDetector()
    zones = ZoneDetector()
    events: list[dict] = []

    if len(frame_5m) < 30 or len(frame_15m) < 8:
        return events

    for i in range(29, len(frame_5m)):
        close_at = frame_5m["timestamp"].iloc[i] + pd.Timedelta(minutes=5)
        completed_15m = frame_15m.loc[
            frame_15m["timestamp"] + pd.Timedelta(minutes=15) <= close_at
        ]
        if len(completed_15m) < 8:
            continue
        htf = trend.analyze(indicator.prepare(completed_15m))
        if htf.side is None:
            continue
        prefix = indicator.prepare(frame_5m.iloc[: i + 1])
        last = prefix.iloc[-1]
        event = trigger.detect(prefix, len(prefix) - 1, htf.side)
        if not event.valid:
            continue
        eligible = zones.detect(prefix)
        side_zones = [zone for zone in eligible if zone.aligns(htf.side)]
        zone_list = [
            {"type": z.zone_type, "low": round(z.low, 4), "high": round(z.high, 4)}
            for z in side_zones if z.zone_type in ("fair_value_gap", "order_block")
        ]
        events.append({
            "asof_close_utc": close_at.isoformat(),
            "spot_close": round(float(last["close"]), 4),
            "15m_trend": htf.trend,
            "5m_trigger": event.trigger_type,
            "side": htf.side,
            "15m_history_bars": len(completed_15m),
            "candidate_zones": zone_list,
            "status": "AUDIT_ONLY_NOT_AN_ORDER",
        })
    return events


def make_report(frame_5m: pd.DataFrame, *, source: str) -> dict:
    fifteen = resample_complete(frame_5m, source_minutes=5, target_minutes=15)
    if len(frame_5m) < 30 or len(fifteen) < 8:
        raise ReplayDataError("Insufficient complete 5m/15m bars for historical replay.")
    events = replay(frame_5m)
    cutoff_index = len(frame_5m) // 2
    historical_prefix = frame_5m.iloc[:cutoff_index]
    if len(historical_prefix) >= 30:
        earlier = replay(historical_prefix)
        cutoff = historical_prefix["timestamp"].iloc[-1] + pd.Timedelta(minutes=5)
        comparable = [event for event in events if pd.Timestamp(event["asof_close_utc"]) <= cutoff]
        if comparable != earlier:
            raise ReplayDataError("FAIL: signals changed when future candles were appended.")
    return {
        "instrument": "NIFTY_SPOT",
        "source": source,
        "status": "CAUSAL_TIMING_AUDITED_NOT_PROFIT_BACKTEST",
        "first_candle_utc": frame_5m["timestamp"].iloc[0].isoformat(),
        "last_candle_utc": frame_5m["timestamp"].iloc[-1].isoformat(),
        "complete_5m_bars": len(frame_5m),
        "complete_15m_bars": len(fifteen),
        "prefix_invariance": "PASS",
        "candidate_event_count": len(events),
        "candidate_events": events,
        "limitations": [
            "No options premiums, contract lot sizing, slippage, fees or P&L.",
            "No order placement. Never use this audit as a live-trading approval.",
            "15m trend/5m trigger is an audit of causal signals, not full 4H/1H MTFA order execution.",
            "Requires verified timestamp convention and authentic historical data.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", type=Path, help="Historical 1m or 5m OHLC CSV")
    group.add_argument("--from-db", action="store_true", help="Read-only query of stored NIFTY 1m candles")
    parser.add_argument("--start", help="DB range start, YYYY-MM-DD")
    parser.add_argument("--end", help="DB range end, YYYY-MM-DD")
    parser.add_argument("--source-minutes", type=int, choices=(1, 5), default=5)
    parser.add_argument("--timestamp-role", choices=("open", "close"), required=True)
    parser.add_argument("--assume-naive-timezone", help="Required for timezone-naive CSV/DB timestamps")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.from_db:
            if not args.start or not args.end:
                raise ReplayDataError("--start and --end are required for --from-db.")
            source = load_db_candles(args.start, args.end)
            src_minutes = 1
            descriptor = f"DB NIFTY 1m {args.start}..{args.end}"
        else:
            source = pd.read_csv(args.csv)
            src_minutes = args.source_minutes
            descriptor = str(args.csv)
        provenance = validate_market_provenance(source)
        normalized = normalize_candles(
            source, source_minutes=src_minutes,
            timestamp_role=args.timestamp_role,
            assume_naive_timezone=args.assume_naive_timezone,
        )
        fivemin = (
            resample_complete(normalized, source_minutes=1, target_minutes=5)
            if src_minutes == 1 else normalized
        )
        report = make_report(fivemin, source=descriptor)
        report["provider_label_counts"] = provenance
        report["provenance_note"] = "Source labels alone do not certify quote authenticity."
    except (ReplayDataError, FileNotFoundError) as exc:
        parser.exit(2, f"REPLAY NOT EXECUTED: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        key: report[key] for key in (
            "status", "source", "complete_5m_bars", "complete_15m_bars",
            "prefix_invariance", "candidate_event_count"
        )
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
