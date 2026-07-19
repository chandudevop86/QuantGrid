from __future__ import annotations

from typing import Any

# 1. Fixed NameError: Initialize the flag before evaluation
PROMETHEUS_AVAILABLE = True

try:
    from prometheus_client import (
        Counter as PromCounter,
        Gauge as PromGauge,
        Histogram as PromHistogram,
        REGISTRY as PROM_REGISTRY,
    )
except Exception:  # pragma: no cover
    PROM_REGISTRY = None
    PromCounter = None
    PromGauge = None
    PromHistogram = None
    PROMETHEUS_AVAILABLE = False


def _metric(metric_type: Any, name: str, documentation: str, labels: tuple[str, ...]) -> Any:
    try:
        return metric_type(name, documentation, labels)
    except ValueError:
        names_to_collectors = getattr(PROM_REGISTRY, "_names_to_collectors", {}) if PROM_REGISTRY is not None else {}
        lookup_names = [name]
        if metric_type is PromCounter and name.endswith("_total"):
            base_name = name.removesuffix("_total")
            lookup_names.extend([base_name, f"{base_name}_total", f"{base_name}_created"])
        for lookup_name in lookup_names:
            existing = names_to_collectors.get(lookup_name)
            if existing is not None:
                return existing
        raise


# 2. Fixed Syntax and Indentation: Using standard conditional flow control
if PROMETHEUS_AVAILABLE and PromCounter is not None and PromGauge is not None and PromHistogram is not None:
    candle_validation_total = _metric(
        PromCounter,
        "candle_validation_total",
        "Candle validation decisions.",
        ("status", "valid"),
    )
    candle_feed_delay_seconds = _metric(
        PromGauge,
        "candle_feed_delay_seconds",
        "Latest market data feed delay in seconds.",
        ("status",),
    )
    paper_orders_total = _metric(
        PromCounter,
        "paper_orders_total",
        "Paper order submissions.",
        ("status", "strategy", "symbol"),
    )
    rejected_orders_total = _metric(
        PromCounter,
        "rejected_orders_total",
        "Rejected order attempts.",
        ("reason", "mode"),
    )
    rejected_signals_total = _metric(
        PromCounter,
        "rejected_signals_total",
        "Rejected signal decisions.",
        ("strategy", "reason"),
    )
    signal_generation_total = _metric(
        PromCounter,
        "signal_generation_total",
        "Signal generation attempts.",
        ("strategy", "status"),
    )
    strategy_executions_total = _metric(
        PromCounter,
        "strategy_executions_total",
        "Strategy execution attempts.",
        ("strategy", "status"),
    )
    strategy_signals_total = _metric(
        PromCounter,
        "strategy_signals_total",
        "Signals emitted by strategy executions.",
        ("strategy",),
    )
    failed_strategy_executions_total = _metric(
        PromCounter,
        "failed_strategy_executions_total",
        "Failed strategy executions.",
        ("strategy", "error_type"),
    )
    option_chain_fetch_failures_total = _metric(
        PromCounter,
        "option_chain_fetch_failures_total",
        "Option-chain provider fetch failures.",
        ("provider", "reason"),
    )
    option_chain_failures_total = _metric(
        PromCounter,
        "option_chain_failures_total",
        "Option-chain failures.",
        ("provider", "reason"),
    )
    websocket_disconnect_total = _metric(
        PromCounter,
        "websocket_disconnect_total",
        "WebSocket disconnects.",
        ("reason",),
    )
    market_data_age_seconds = _metric(
        PromGauge,
        "market_data_age_seconds",
        "Latest market data age in seconds.",
        ("symbol", "interval"),
    )
    api_request_latency_seconds = _metric(
        PromHistogram,
        "api_request_latency_seconds",
        "API request latency in seconds.",
        ("method", "path", "status_code"),
    )
    market_data_ticks_total = _metric(
        PromCounter,
        "market_data_ticks_total",
        "Market data ticks received.",
        ("provider", "symbol"),
    )
    market_data_provider_errors_total = _metric(
        PromCounter,
        "market_data_provider_errors_total",
        "Market data provider errors.",
        ("provider", "operation"),
    )
    market_data_feed_delay_seconds = _metric(
        PromGauge,
        "market_data_feed_delay_seconds",
        "Market data feed delay in seconds.",
        ("provider", "symbol"),
    )
    market_data_cache_hits_total = _metric(
        PromCounter,
        "market_data_cache_hits_total",
        "Market data cache hits.",
        ("provider", "kind"),
    )
    market_data_cache_misses_total = _metric(
        PromCounter,
        "market_data_cache_misses_total",
        "Market data cache misses.",
        ("provider", "kind"),
    )
    trading_decisions_total = _metric(
        PromCounter,
        "trading_decisions_total",
        "Dashboard trading decisions.",
        ("recommendation", "data_status", "blocked"),
    )
    risk_blocks_total = _metric(
        PromCounter,
        "risk_blocks_total",
        "Risk blocks by reason.",
        ("reason",),
    )
else:
    candle_validation_total = None
    candle_feed_delay_seconds = None
    paper_orders_total = None
    rejected_orders_total = None
    signal_generation_total = None
    api_request_latency_seconds = None
    market_data_ticks_total = None
    market_data_provider_errors_total = None
    market_data_feed_delay_seconds = None
    market_data_cache_hits_total = None
    market_data_cache_misses_total = None
    strategy_executions_total = None
    strategy_signals_total = None
    failed_strategy_executions_total = None
    option_chain_fetch_failures_total = None
    option_chain_failures_total = None
    rejected_signals_total = None
    websocket_disconnect_total = None
    market_data_age_seconds = None
    trading_decisions_total = None
    risk_blocks_total = None


def observe_candle_validation(status: str, valid: bool, delay_seconds: int | None) -> None:
    if candle_validation_total is not None:
        candle_validation_total.labels(status=status, valid=str(valid).lower()).inc()
    if candle_feed_delay_seconds is not None and delay_seconds is not None:
        candle_feed_delay_seconds.labels(status=status).set(delay_seconds)


def observe_paper_order(status: str, strategy: str | None, symbol: str | None) -> None:
    if paper_orders_total is not None:
        paper_orders_total.labels(
            status=status, strategy=strategy or "unknown", symbol=(symbol or "unknown").upper()
        ).inc()


def observe_rejected_order(reason: str | None, mode: str | None) -> None:
    if rejected_orders_total is not None:
        rejected_orders_total.labels(reason=reason or "unknown", mode=mode or "unknown").inc()


def observe_rejected_signal(strategy: str | None, reason: str | None = None) -> None:
    if rejected_signals_total is not None:
        rejected_signals_total.labels(strategy=strategy or "unknown", reason=reason or "unknown").inc()


def observe_signal_generation(strategy: str | None, status: str) -> None:
    if signal_generation_total is not None:
        signal_generation_total.labels(strategy=strategy or "unknown", status=status).inc()


def observe_strategy_execution(
    strategy: str | None, status: str, signal_count: int = 0, error_type: str | None = None
) -> None:
    strategy_name = strategy or "unknown"
    if strategy_executions_total is not None:
        strategy_executions_total.labels(strategy=strategy_name, status=status).inc()
    if strategy_signals_total is not None and signal_count > 0:
        strategy_signals_total.labels(strategy=strategy_name).inc(signal_count)
    if failed_strategy_executions_total is not None and status == "failed":
        failed_strategy_executions_total.labels(strategy=strategy_name, error_type=error_type or "unknown").inc()


# 3. Fixed typos: Completed incomplete trailing function wrapper block
def observe_option_chain_failure(provider: str, reason: str | None = None) -> None:
    if option_chain_fetch_failures_total is not None:
        option_chain_fetch_failures_total.labels(provider=provider, reason=reason or "unknown").inc()
    if option_chain_failures_total is not None:
        option_chain_failures_total.labels(provider=provider, reason=reason or "unknown").inc()
