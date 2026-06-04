from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from Backend.application.monitoring import observe_candle_validation

logger = logging.getLogger(__name__)

NSE_TIMEZONE = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

MarketStatus = Literal["PREMARKET", "LIVE MARKET", "DELAYED FEED", "MARKET CLOSED", "HOLIDAY", "WEEKEND"]
ValidationMode = Literal["live", "paper", "backtest"]

DEFAULT_NSE_HOLIDAYS = {
    "2026-01-26",
    "2026-03-03",
    "2026-03-31",
    "2026-04-03",
    "2026-04-14",
    "2026-05-01",
    "2026-08-15",
    "2026-10-02",
    "2026-11-09",
    "2026-12-25",
}


class CandleValidationSettings(BaseModel):
    timezone_name: str = "Asia/Kolkata"
    premarket_start: time = time(9, 0)
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    warning_after_seconds: int = Field(default=120, ge=0)
    reject_after_seconds: int = Field(default=300, ge=1)
    delayed_feed_tolerance_seconds: int = Field(default=60, ge=0)
    max_missing_candles: int = Field(default=2, ge=0)
    holidays: set[str] = Field(default_factory=lambda: set(DEFAULT_NSE_HOLIDAYS))


class FeedDelay(BaseModel):
    delay_seconds: int | None
    provider_latency_seconds: int | None = None
    stale_duration_seconds: int | None = None
    missing_candles: int = 0


class CandleValidationResult(BaseModel):
    valid: bool
    valid_for_analysis: bool
    valid_for_execution: bool
    market_live: bool
    market_status: str
    ui_status: str
    delay_seconds: int | None
    provider_latency_seconds: int | None = None
    stale_duration_seconds: int | None = None
    missing_candles: int = 0
    latest_candle: str | None
    latest_candle_ist: str | None
    server_time: str
    server_time_ist: str
    diagnostics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MarketSession:
    status: MarketStatus
    market_live: bool
    is_trading_day: bool
    session_open: datetime | None
    session_close: datetime | None
    reason: str


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def validation_settings() -> CandleValidationSettings:
    holidays = set(DEFAULT_NSE_HOLIDAYS)
    configured = os.getenv("QUANTGRID_NSE_HOLIDAYS", "")
    holidays.update(item.strip() for item in configured.split(",") if item.strip())
    return CandleValidationSettings(
        warning_after_seconds=_int_env("QUANTGRID_CANDLE_WARNING_SECONDS", 120),
        reject_after_seconds=_int_env("QUANTGRID_CANDLE_REJECT_SECONDS", 300),
        delayed_feed_tolerance_seconds=_int_env("QUANTGRID_FEED_DELAY_TOLERANCE_SECONDS", 60),
        max_missing_candles=_int_env("QUANTGRID_MAX_MISSING_CANDLES", 2),
        holidays=holidays,
    )


def normalize_timestamp(value: Any, *, assume_timezone: ZoneInfo | timezone = NSE_TIMEZONE) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).astimezone(NSE_TIMEZONE)
    try:
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=assume_timezone)
    return timestamp.astimezone(NSE_TIMEZONE)


def _holiday_set(settings: CandleValidationSettings | None = None) -> set[date]:
    settings = settings or validation_settings()
    holidays: set[date] = set()
    for item in settings.holidays:
        try:
            holidays.add(date.fromisoformat(item))
        except ValueError:
            logger.warning("Ignoring invalid NSE holiday date: %s", item)
    return holidays


def get_market_session(
    now: datetime | None = None,
    *,
    settings: CandleValidationSettings | None = None,
) -> MarketSession:
    settings = settings or validation_settings()
    current = normalize_timestamp(now or datetime.now(UTC)) or datetime.now(NSE_TIMEZONE)
    current_date = current.date()
    session_open = datetime.combine(current_date, settings.market_open, NSE_TIMEZONE)
    session_close = datetime.combine(current_date, settings.market_close, NSE_TIMEZONE)
    premarket_start = datetime.combine(current_date, settings.premarket_start, NSE_TIMEZONE)

    if current.weekday() >= 5:
        return MarketSession("WEEKEND", False, False, session_open, session_close, "NSE is closed on weekends.")
    if current_date in _holiday_set(settings):
        return MarketSession("HOLIDAY", False, False, session_open, session_close, "NSE holiday; stale checks disabled.")
    if premarket_start <= current < session_open:
        return MarketSession("PREMARKET", False, True, session_open, session_close, "NSE premarket window.")
    if session_open <= current <= session_close:
        return MarketSession("LIVE MARKET", True, True, session_open, session_close, "NSE regular market is open.")
    return MarketSession("MARKET CLOSED", False, True, session_open, session_close, "NSE regular market is closed.")


def is_market_open(now: datetime | None = None) -> bool:
    return get_market_session(now).market_live


def _interval_seconds(interval: str | None) -> int:
    value = (interval or "1m").strip().lower()
    try:
        if value.endswith("m"):
            return max(60, int(value[:-1]) * 60)
        if value.endswith("h"):
            return max(60, int(value[:-1]) * 3600)
        if value.endswith("d"):
            return max(60, int(value[:-1]) * 86400)
    except ValueError:
        return 60
    return 60


def detect_feed_delay(
    latest_candle: Any,
    *,
    now: datetime | None = None,
    interval: str = "1m",
    provider_fetched_at: Any = None,
    settings: CandleValidationSettings | None = None,
) -> FeedDelay:
    settings = settings or validation_settings()
    current = normalize_timestamp(now or datetime.now(UTC)) or datetime.now(NSE_TIMEZONE)
    latest = normalize_timestamp(latest_candle)
    fetched_at = normalize_timestamp(provider_fetched_at) if provider_fetched_at else None
    if latest is None:
        return FeedDelay(delay_seconds=None, provider_latency_seconds=None, stale_duration_seconds=None)

    delay_seconds = max(0, int((current - latest).total_seconds()))
    provider_latency = max(0, int((current - fetched_at).total_seconds())) if fetched_at else None
    stale_duration = max(0, delay_seconds - settings.warning_after_seconds)
    missing = max(0, delay_seconds // _interval_seconds(interval) - 1)
    return FeedDelay(
        delay_seconds=delay_seconds,
        provider_latency_seconds=provider_latency,
        stale_duration_seconds=stale_duration,
        missing_candles=missing,
    )


def _status_icon(status: str) -> str:
    if status == "LIVE MARKET":
        return "🟢 LIVE MARKET"
    if status == "DELAYED FEED":
        return "🟡 DELAYED FEED"
    if status == "HOLIDAY":
        return "⚫ HOLIDAY"
    if status == "WEEKEND":
        return "⚫ WEEKEND"
    return f"🔴 {status}"


def validate_live_candle(
    candles: list[dict[str, Any]],
    *,
    interval: str = "1m",
    mode: ValidationMode = "paper",
    source: str | None = None,
    now: datetime | None = None,
    provider_fetched_at: Any = None,
    settings: CandleValidationSettings | None = None,
) -> CandleValidationResult:
    settings = settings or validation_settings()
    current = normalize_timestamp(now or datetime.now(UTC)) or datetime.now(NSE_TIMEZONE)
    session = get_market_session(current, settings=settings)
    latest_raw = candles[-1].get("timestamp") if candles else None
    latest = normalize_timestamp(latest_raw)
    delay = detect_feed_delay(
        latest,
        now=current,
        interval=interval,
        provider_fetched_at=provider_fetched_at,
        settings=settings,
    )
    diagnostics: list[str] = []
    warnings: list[str] = []

    if mode == "backtest":
        diagnostics.append("Backtest mode: live stale-candle rejection is disabled.")
        result = CandleValidationResult(
            valid=latest is not None,
            valid_for_analysis=latest is not None,
            valid_for_execution=False,
            market_live=False,
            market_status="BACKTEST",
            ui_status="⚫ BACKTEST",
            delay_seconds=delay.delay_seconds,
            provider_latency_seconds=delay.provider_latency_seconds,
            stale_duration_seconds=delay.stale_duration_seconds,
            missing_candles=delay.missing_candles,
            latest_candle=latest.astimezone(UTC).isoformat() if latest else None,
            latest_candle_ist=latest.isoformat() if latest else None,
            server_time=current.astimezone(UTC).isoformat(),
            server_time_ist=current.isoformat(),
            diagnostics=diagnostics,
            warnings=warnings,
        )
        observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
        return result

    if latest is None:
        diagnostics.append("No latest candle timestamp is available.")
        result = CandleValidationResult(
            valid=False,
            valid_for_analysis=False,
            valid_for_execution=False,
            market_live=session.market_live,
            market_status=session.status,
            ui_status=_status_icon(session.status),
            delay_seconds=None,
            latest_candle=None,
            latest_candle_ist=None,
            server_time=current.astimezone(UTC).isoformat(),
            server_time_ist=current.isoformat(),
            diagnostics=diagnostics,
            warnings=warnings,
        )
        observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
        return result

    if mode == "live":
        source_name = str(source or "").lower()
        allow_yahoo_live = os.getenv("QUANTGRID_ALLOW_YAHOO_LIVE") or os.getenv("QUANTGRID_ALLOW_YAHOO_FOR_LIVE")
        if source_name in {"yahoo", "yahoo-finance", "demo", "sample", "sample-fallback"} and str(allow_yahoo_live or "false").strip().lower() not in {"1", "true", "yes"}:
            diagnostics.append("Yahoo/sample data is paper/demo only and is not allowed for live execution.")
            result = CandleValidationResult(
                valid=False,
                valid_for_analysis=False,
                valid_for_execution=False,
                market_live=session.market_live,
                market_status="DELAYED FEED",
                ui_status=_status_icon("DELAYED FEED"),
                delay_seconds=delay.delay_seconds,
                provider_latency_seconds=delay.provider_latency_seconds,
                stale_duration_seconds=delay.stale_duration_seconds,
                missing_candles=delay.missing_candles,
                latest_candle=latest.astimezone(UTC).isoformat(),
                latest_candle_ist=latest.isoformat(),
                server_time=current.astimezone(UTC).isoformat(),
                server_time_ist=current.isoformat(),
                diagnostics=diagnostics,
                warnings=warnings,
            )
            observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
            return result
        latest_candle = candles[-1]
        exchange_timezone = latest_candle.get("exchange_timezone")
        if str(exchange_timezone or "") != "Asia/Kolkata":
            diagnostics.append(f"Live market data timestamp timezone must be Asia/Kolkata; got {exchange_timezone}.")
            result = CandleValidationResult(
                valid=False,
                valid_for_analysis=False,
                valid_for_execution=False,
                market_live=session.market_live,
                market_status="DELAYED FEED",
                ui_status=_status_icon("DELAYED FEED"),
                delay_seconds=delay.delay_seconds,
                provider_latency_seconds=delay.provider_latency_seconds,
                stale_duration_seconds=delay.stale_duration_seconds,
                missing_candles=delay.missing_candles,
                latest_candle=latest.astimezone(UTC).isoformat(),
                latest_candle_ist=latest.isoformat(),
                server_time=current.astimezone(UTC).isoformat(),
                server_time_ist=current.isoformat(),
                diagnostics=diagnostics,
                warnings=warnings,
            )
            observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
            return result
        try:
            latest_close = float(latest_candle.get("close"))
        except (TypeError, ValueError):
            latest_close = 0.0
        if latest_close <= 0:
            diagnostics.append("Live market data latest candle close must be greater than zero.")
            result = CandleValidationResult(
                valid=False,
                valid_for_analysis=False,
                valid_for_execution=False,
                market_live=session.market_live,
                market_status="DELAYED FEED",
                ui_status=_status_icon("DELAYED FEED"),
                delay_seconds=delay.delay_seconds,
                provider_latency_seconds=delay.provider_latency_seconds,
                stale_duration_seconds=delay.stale_duration_seconds,
                missing_candles=delay.missing_candles,
                latest_candle=latest.astimezone(UTC).isoformat(),
                latest_candle_ist=latest.isoformat(),
                server_time=current.astimezone(UTC).isoformat(),
                server_time_ist=current.isoformat(),
                diagnostics=diagnostics,
                warnings=warnings,
            )
            observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
            return result

    if delay.delay_seconds is not None:
        diagnostics.append(
            f"Latest candle {latest.isoformat()} IST from {source or 'unknown'} feed; "
            f"age {delay.delay_seconds}s, limit {settings.reject_after_seconds}s."
        )
    else:
        diagnostics.append(f"Latest candle {latest.isoformat()} IST from {source or 'unknown'} feed.")
    diagnostics.append(session.reason)

    if not session.market_live:
        warnings.append(f"{session.status}: stale rejection disabled; final/latest candle analysis is allowed.")
        result = CandleValidationResult(
            valid=True,
            valid_for_analysis=True,
            valid_for_execution=False,
            market_live=False,
            market_status=session.status,
            ui_status=_status_icon(session.status),
            delay_seconds=delay.delay_seconds,
            provider_latency_seconds=delay.provider_latency_seconds,
            stale_duration_seconds=delay.stale_duration_seconds,
            missing_candles=delay.missing_candles,
            latest_candle=latest.astimezone(UTC).isoformat(),
            latest_candle_ist=latest.isoformat(),
            server_time=current.astimezone(UTC).isoformat(),
            server_time_ist=current.isoformat(),
            diagnostics=diagnostics,
            warnings=warnings,
        )
        observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
        return result

    delayed_limit = settings.reject_after_seconds + settings.delayed_feed_tolerance_seconds
    if delay.delay_seconds is not None and delay.delay_seconds > settings.warning_after_seconds:
        warnings.append(
            f"Feed delay is {delay.delay_seconds}s; warning threshold is {settings.warning_after_seconds}s."
        )
    if delay.missing_candles > settings.max_missing_candles:
        warnings.append(f"Possible missing candles detected: {delay.missing_candles}.")
    valid = delay.delay_seconds is not None and delay.delay_seconds <= delayed_limit
    if mode == "live" and delay.missing_candles > settings.max_missing_candles:
        valid = False
        diagnostics.append(
            f"Missing candle count {delay.missing_candles} exceeds live limit {settings.max_missing_candles}."
        )
    status = "LIVE MARKET" if valid and delay.delay_seconds <= settings.warning_after_seconds else "DELAYED FEED"
    if not valid:
        diagnostics.append(
            f"Latest candle is stale during live market: delay {delay.delay_seconds}s, "
            f"reject threshold {settings.reject_after_seconds}s plus tolerance "
            f"{settings.delayed_feed_tolerance_seconds}s."
        )

    result = CandleValidationResult(
        valid=valid,
        valid_for_analysis=valid,
        valid_for_execution=valid and status == "LIVE MARKET",
        market_live=True,
        market_status=status,
        ui_status=_status_icon(status),
        delay_seconds=delay.delay_seconds,
        provider_latency_seconds=delay.provider_latency_seconds,
        stale_duration_seconds=delay.stale_duration_seconds,
        missing_candles=delay.missing_candles,
        latest_candle=latest.astimezone(UTC).isoformat(),
        latest_candle_ist=latest.isoformat(),
        server_time=current.astimezone(UTC).isoformat(),
        server_time_ist=current.isoformat(),
        diagnostics=diagnostics,
        warnings=warnings,
    )
    observe_candle_validation(result.market_status, result.valid, result.delay_seconds)
    return result
