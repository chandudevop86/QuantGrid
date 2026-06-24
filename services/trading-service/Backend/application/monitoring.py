from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover - optional production dependency
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]


if Counter and Gauge and Histogram:
    candle_validation_total = Counter(
        "candle_validation_total",
        "Candle validation decisions.",
        ("status", "valid"),
    )
    candle_feed_delay_seconds = Gauge(
        "candle_feed_delay_seconds",
        "Latest market data feed delay in seconds.",
        ("status",),
    )
    paper_orders_total = Counter(
        "paper_orders_total",
        "Paper order submissions.",
        ("status", "strategy", "symbol"),
    )
    rejected_orders_total = Counter(
        "rejected_orders_total",
        "Rejected order attempts.",
        ("reason", "mode"),
    )
    signal_generation_total = Counter(
        "signal_generation_total",
        "Signal generation attempts.",
        ("strategy", "status"),
    )
    strategy_executions_total = Counter(
        "strategy_executions_total",
        "Strategy execution attempts.",
        ("strategy", "status"),
    )
    strategy_signals_total = Counter(
        "strategy_signals_total",
        "Signals emitted by strategy executions.",
        ("strategy",),
    )
    failed_strategy_executions_total = Counter(
        "failed_strategy_executions_total",
        "Failed strategy executions.",
        ("strategy", "error_type"),
    )
    option_chain_fetch_failures_total = Counter(
        "option_chain_fetch_failures_total",
        "Option-chain provider fetch failures.",
        ("provider", "reason"),
    )
    api_request_latency_seconds = Histogram(
        "api_request_latency_seconds",
        "API request latency in seconds.",
        ("method", "path", "status_code"),
    )
    market_data_ticks_total = Counter(
        "market_data_ticks_total",
        "Market data ticks received.",
        ("provider", "symbol"),
    )
    market_data_provider_errors_total = Counter(
        "market_data_provider_errors_total",
        "Market data provider errors.",
        ("provider", "operation"),
    )
    market_data_feed_delay_seconds = Gauge(
        "market_data_feed_delay_seconds",
        "Market data feed delay in seconds.",
        ("provider", "symbol"),
    )
    market_data_cache_hits_total = Counter(
        "market_data_cache_hits_total",
        "Market data cache hits.",
        ("provider", "kind"),
    )
    market_data_cache_misses_total = Counter(
        "market_data_cache_misses_total",
        "Market data cache misses.",
        ("provider", "kind"),
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


def observe_candle_validation(status: str, valid: bool, delay_seconds: int | None) -> None:
    if candle_validation_total is not None:
        candle_validation_total.labels(status=status, valid=str(valid).lower()).inc()
    if candle_feed_delay_seconds is not None and delay_seconds is not None:
        candle_feed_delay_seconds.labels(status=status).set(delay_seconds)


def observe_paper_order(status: str, strategy: str | None, symbol: str | None) -> None:
    if paper_orders_total is not None:
        paper_orders_total.labels(status=status, strategy=strategy or "unknown", symbol=(symbol or "unknown").upper()).inc()


def observe_rejected_order(reason: str | None, mode: str | None) -> None:
    if rejected_orders_total is not None:
        rejected_orders_total.labels(reason=reason or "unknown", mode=mode or "unknown").inc()


def observe_signal_generation(strategy: str | None, status: str) -> None:
    if signal_generation_total is not None:
        signal_generation_total.labels(strategy=strategy or "unknown", status=status).inc()


def observe_strategy_execution(strategy: str | None, status: str, signal_count: int = 0, error_type: str | None = None) -> None:
    strategy_name = strategy or "unknown"
    if strategy_executions_total is not None:
        strategy_executions_total.labels(strategy=strategy_name, status=status).inc()
    if strategy_signals_total is not None and signal_count > 0:
        strategy_signals_total.labels(strategy=strategy_name).inc(signal_count)
    if failed_strategy_executions_total is not None and status == "failed":
        failed_strategy_executions_total.labels(strategy=strategy_name, error_type=error_type or "unknown").inc()


def observe_option_chain_failure(provider: str, reason: str | None = None) -> None:
    if option_chain_fetch_failures_total is not None:
        option_chain_fetch_failures_total.labels(provider=provider, reason=reason or "unknown").inc()


def observe_api_request(method: str, path: str, status_code: int, latency_seconds: float) -> None:
    if api_request_latency_seconds is not None:
        api_request_latency_seconds.labels(method=method, path=path, status_code=str(status_code)).observe(latency_seconds)


def observe_market_data_tick(provider: str, symbol: str) -> None:
    if market_data_ticks_total is not None:
        market_data_ticks_total.labels(provider=provider, symbol=symbol.upper()).inc()


def observe_market_data_error(provider: str, operation: str) -> None:
    if market_data_provider_errors_total is not None:
        market_data_provider_errors_total.labels(provider=provider, operation=operation).inc()


def observe_market_data_delay(provider: str, symbol: str, delay_seconds: int | float | None) -> None:
    if market_data_feed_delay_seconds is not None and delay_seconds is not None:
        market_data_feed_delay_seconds.labels(provider=provider, symbol=symbol.upper()).set(float(delay_seconds))


def observe_market_data_cache(provider: str, kind: str, hit: bool) -> None:
    metric = market_data_cache_hits_total if hit else market_data_cache_misses_total
    if metric is not None:
        metric.labels(provider=provider, kind=kind).inc()
