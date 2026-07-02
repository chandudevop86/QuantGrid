from __future__ import annotations

from typing import Any

from Backend.application.fno_narrative_service import _option_chain_payload
from Backend.application.investment_research_service import sample_stock_universe
from Backend.application.market_data_service import get_market_data_service
from Backend.application.market_data_store import latest_candles
from app.validation.data_quality import (
    DataQualityReport,
    validate_candles,
    validate_fundamental_snapshot,
    validate_option_chain_rows,
    validate_provider_quality,
)


def build_data_quality_dashboard(symbol: str = "NIFTY", interval: str = "1m") -> dict[str, Any]:
    symbol = symbol.upper()
    reports: list[DataQualityReport] = []

    candles = latest_candles(symbol, interval, 100)
    _valid_candles, candle_report = validate_candles(candles, source="stored-live-cache" if candles else "unknown")
    reports.append(candle_report)

    try:
        provider_payload = get_market_data_service().health(symbol=symbol, interval=interval)
        provider_report = DataQualityReport(
            subject="provider",
            status="PASS" if provider_payload.get("fresh") else "WARN",
            quality_score=validate_provider_quality(
                source=str(provider_payload.get("provider") or provider_payload.get("source") or "unknown"),
                rows=[provider_payload],
                missing_fields=[] if provider_payload.get("fresh") else ["freshness"],
                fallback=not bool(provider_payload.get("live_suitable")),
                fresh=bool(provider_payload.get("fresh")),
            ).quality_score,
            source=str(provider_payload.get("provider") or provider_payload.get("source") or "unknown"),
            rows_checked=1,
            warnings=[] if provider_payload.get("fresh") else ["Provider feed is stale or unavailable."],
            provider=validate_provider_quality(
                source=str(provider_payload.get("provider") or provider_payload.get("source") or "unknown"),
                rows=[provider_payload],
                missing_fields=[] if provider_payload.get("fresh") else ["freshness"],
                fallback=not bool(provider_payload.get("live_suitable")),
                fresh=bool(provider_payload.get("fresh")),
            ),
        )
    except Exception as exc:
        provider_report = DataQualityReport(
            subject="provider",
            status="FAIL",
            quality_score=0,
            source="unknown",
            rows_checked=0,
            errors=[f"provider health unavailable: {exc}"],
        )
    reports.append(provider_report)

    try:
        chain_payload = _option_chain_payload(symbol)
        _valid_rows, option_report = validate_option_chain_rows(
            list(chain_payload.get("rows") or []),
            source=str(chain_payload.get("source") or "unknown"),
        )
    except Exception as exc:
        option_report = DataQualityReport(
            subject="option_chain",
            status="FAIL",
            quality_score=0,
            source="unknown",
            rows_checked=0,
            errors=[f"option chain unavailable: {exc}"],
        )
    reports.append(option_report)

    stock_reports = [
        validate_fundamental_snapshot(stock.model_dump(), source="sample-investing-universe")
        for stock in sample_stock_universe()
    ]
    if stock_reports:
        average_score = int(sum(report.quality_score for report in stock_reports) / len(stock_reports))
        missing_fields = sorted({field for report in stock_reports for field in report.missing_fields})
        reports.append(
            DataQualityReport(
                subject="fundamentals",
                status="PASS" if average_score >= 80 else "WARN" if average_score >= 50 else "FAIL",
                quality_score=average_score,
                source="sample-investing-universe",
                rows_checked=len(stock_reports),
                missing_fields=missing_fields,
                warnings=["Some stock fundamentals are unavailable."] if missing_fields else [],
            )
        )

    overall = int(sum(report.quality_score for report in reports) / max(len(reports), 1))
    return {
        "symbol": symbol,
        "interval": interval,
        "overall_status": "PASS" if overall >= 80 else "WARN" if overall >= 50 else "FAIL",
        "overall_quality_score": overall,
        "reports": [report.model_dump() for report in reports],
    }
