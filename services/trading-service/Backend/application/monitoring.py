from __future__ import annotations

from typing import Any


try:
    from prometheus_client import (
        REGISTRY as PROM_REGISTRY,
        Counter as PromCounter,
        Gauge as PromGauge,
        Histogram as PromHistogram,
    )
except Exception:  # pragma: no cover
    PROM_REGISTRY = None
    PromCounter = None
    PromGauge = None
    PromHistogram = None

if (
    PromCounter is not None
    and PromGauge is not None
    and PromHistogram is not None
):
    ...
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
        paper_orders_total.labels(status=status, strategy=strategy or "unknown", symbol=(symbol or "unknown").upper()).inc()


def observe_rejected_order(reason: str | None, mode: str | None) -> None:
    if rejected_orders_total is not None:
        rejected_orders_total.labels(reason=reason or "unknown", mode=mode or "unknown").inc()


def observe_rejected_signal(strategy: str | None, reason: str | None = None) -> None:
    if rejected_signals_total is not None:
        rejected_signals_total.labels(strategy=strategy or "unknown", reason=reason or "unknown").inc()


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
    if option_chain_failures_total is not None:
        option_chain_failures_total.labels(provider=provider, reason=reason or "unknown").inc()


def observe_websocket_disconnect(reason: str | None = None) -> None:
    if websocket_disconnect_total is not None:
        websocket_disconnect_total.labels(reason=reason or "unknown").inc()


def observe_market_data_age(symbol: str, interval: str, age_seconds: int | float | None) -> None:
    if market_data_age_seconds is not None and age_seconds is not None:
        market_data_age_seconds.labels(symbol=symbol.upper(), interval=interval).set(float(age_seconds))


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


def observe_trading_decision(recommendation: str, data_status: str, blocked: bool) -> None:
    if trading_decisions_total is not None:
        trading_decisions_total.labels(
            recommendation=recommendation or "unknown",
            data_status=data_status or "unknown",
            blocked=str(bool(blocked)).lower(),
        ).inc()


def observe_risk_block(reason: str | None) -> None:
    if risk_blocks_total is not None:
        risk_blocks_total.labels(reason=reason or "unknown").inc()
