from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


class CandleInput(BaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int | None = Field(default=None, ge=0)
    symbol: str | None = None
    exchange_timezone: str | None = None

    @model_validator(mode="after")
    def validate_ohlc(self) -> "CandleInput":
        high = float(self.high)
        low = float(self.low)
        if high < low:
            raise ValueError("high must be greater than or equal to low")
        if not low <= float(self.open) <= high:
            raise ValueError("open must be inside high/low range")
        if not low <= float(self.close) <= high:
            raise ValueError("close must be inside high/low range")
        return self


class OptionChainLeg(BaseModel):
    ltp: float | None = Field(default=None, ge=0)
    change: float | None = None
    volume: int | None = Field(default=None, ge=0)
    oi: float | None = Field(default=None, ge=0)
    iv: float | None = Field(default=None, ge=0)
    oi_change: float | None = None
    change_oi: float | None = None
    changeinOpenInterest: float | None = None
    oiChange: float | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        aliases = {
            "lastPrice": "ltp",
            "last_price": "ltp",
            "openInterest": "oi",
            "open_interest": "oi",
            "impliedVolatility": "iv",
            "implied_volatility": "iv",
            "changeinOpenInterest": "changeinOpenInterest",
        }
        for source, target in aliases.items():
            if target not in normalized and source in normalized:
                normalized[target] = normalized[source]
        return normalized

    @field_validator("iv")
    @classmethod
    def cap_iv(cls, value: float | None) -> float | None:
        if value is not None and value > 500:
            raise ValueError("iv is unrealistically high")
        return value


class OptionChainRow(BaseModel):
    strike: float = Field(gt=0)
    ce: OptionChainLeg = Field(default_factory=OptionChainLeg)
    pe: OptionChainLeg = Field(default_factory=OptionChainLeg)

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "ce" not in normalized and "CE" in normalized:
            normalized["ce"] = normalized["CE"]
        if "pe" not in normalized and "PE" in normalized:
            normalized["pe"] = normalized["PE"]
        return normalized


class FundamentalSnapshot(BaseModel):
    symbol: str
    name: str
    revenue_growth_3y: float | None = None
    profit_growth_3y: float | None = None
    quarterly_revenue_growth: float | None = None
    quarterly_profit_growth: float | None = None
    debt_to_equity: float | None = None
    operating_cash_flow_positive: bool | None = None
    free_cash_flow_positive: bool | None = None
    roe: float | None = None
    roce: float | None = None
    pe: float | None = None
    pb: float | None = None
    eps_growth: float | None = None

    def missing_fields(self) -> list[str]:
        required = [
            "revenue_growth_3y",
            "profit_growth_3y",
            "quarterly_revenue_growth",
            "quarterly_profit_growth",
            "debt_to_equity",
            "operating_cash_flow_positive",
            "free_cash_flow_positive",
            "roe",
            "roce",
            "pe",
            "pb",
            "eps_growth",
        ]
        return [field for field in required if _is_missing(getattr(self, field))]


class ProviderQuality(BaseModel):
    source: str
    freshness: Literal["fresh", "stale", "unknown"]
    completeness_pct: float = Field(ge=0, le=100)
    fallback: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    quality_score: int = Field(ge=0, le=100)


class DataQualityReport(BaseModel):
    subject: str
    status: Literal["PASS", "WARN", "FAIL"]
    quality_score: int = Field(ge=0, le=100)
    source: str | None = None
    rows_checked: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: ProviderQuality | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def validate_candles(candles: list[dict[str, Any]], *, source: str | None = None) -> tuple[list[dict[str, Any]], DataQualityReport]:
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, candle in enumerate(candles):
        try:
            valid.append(CandleInput(**candle).model_dump(mode="json"))
        except ValidationError as exc:
            errors.append(f"candle[{index}]: {exc.errors()[0]['msg']}")
    missing = [] if candles else ["candles"]
    score = _quality_score(total=len(candles), valid=len(valid), missing=len(missing), errors=len(errors), fallback=_is_fallback(source))
    return valid, DataQualityReport(
        subject="candles",
        status=_status(score, errors),
        quality_score=score,
        source=source,
        rows_checked=len(candles),
        missing_fields=missing,
        errors=errors,
        warnings=["Fallback/source is not trading-grade."] if _is_fallback(source) else [],
        provider=validate_provider_quality(source=source, rows=valid, missing_fields=missing, fallback=_is_fallback(source)),
    )


def validate_option_chain_rows(rows: list[dict[str, Any]], *, source: str | None = None) -> tuple[list[dict[str, Any]], DataQualityReport]:
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        try:
            parsed = OptionChainRow(**row)
            valid.append(parsed.model_dump())
        except ValidationError as exc:
            errors.append(f"option_chain[{index}]: {exc.errors()[0]['msg']}")
    missing = [] if rows else ["option_chain"]
    if valid and not any((row["ce"].get("oi") or 0) > 0 or (row["pe"].get("oi") or 0) > 0 for row in valid):
        missing.append("open_interest")
    score = _quality_score(total=len(rows), valid=len(valid), missing=len(missing), errors=len(errors), fallback=_is_fallback(source))
    return valid, DataQualityReport(
        subject="option_chain",
        status=_status(score, errors),
        quality_score=score,
        source=source,
        rows_checked=len(rows),
        missing_fields=missing,
        errors=errors,
        warnings=["Option chain has no open interest; derivative signals are low confidence."] if "open_interest" in missing else [],
        provider=validate_provider_quality(source=source, rows=valid, missing_fields=missing, fallback=_is_fallback(source)),
    )


def validate_fundamental_snapshot(payload: dict[str, Any], *, source: str | None = None) -> DataQualityReport:
    try:
        snapshot = FundamentalSnapshot(**payload)
        missing = snapshot.missing_fields()
        errors: list[str] = []
    except ValidationError as exc:
        missing = []
        errors = [f"fundamentals: {item['msg']}" for item in exc.errors()]
    score = _quality_score(total=1, valid=0 if errors else 1, missing=len(missing), errors=len(errors), fallback=_is_fallback(source))
    return DataQualityReport(
        subject="fundamentals",
        status=_status(score, errors),
        quality_score=score,
        source=source,
        rows_checked=1,
        missing_fields=missing,
        errors=errors,
        warnings=["Missing fundamentals are treated as unavailable, not as zero."] if missing else [],
        provider=validate_provider_quality(source=source, rows=[payload], missing_fields=missing, fallback=_is_fallback(source)),
    )


def validate_provider_quality(
    *,
    source: str | None,
    rows: list[dict[str, Any]],
    missing_fields: list[str],
    fallback: bool,
    fresh: bool | None = None,
) -> ProviderQuality:
    total_fields = max(len(rows) * 5, 1)
    missing_count = len(missing_fields)
    completeness = max(0.0, min(100.0, 100.0 - missing_count / total_fields * 100.0))
    freshness = "unknown" if fresh is None else "fresh" if fresh else "stale"
    score = int(max(0, min(100, completeness - missing_count * 5 - (25 if fallback else 0) - (20 if freshness == "stale" else 0))))
    return ProviderQuality(
        source=str(source or "unknown"),
        freshness=freshness,
        completeness_pct=round(completeness, 2),
        fallback=fallback,
        missing_fields=missing_fields,
        quality_score=score,
    )


def _quality_score(*, total: int, valid: int, missing: int, errors: int, fallback: bool) -> int:
    if total <= 0:
        return 0
    valid_ratio = valid / total
    score = valid_ratio * 100 - missing * 8 - errors * 12 - (25 if fallback else 0)
    return int(max(0, min(100, round(score))))


def _status(score: int, errors: list[str]) -> Literal["PASS", "WARN", "FAIL"]:
    if errors or score < 50:
        return "FAIL"
    if score < 80:
        return "WARN"
    return "PASS"


def _is_fallback(source: str | None) -> bool:
    value = str(source or "").lower()
    return "fallback" in value or "sample" in value or "derived" in value or "stored-live-cache" in value
