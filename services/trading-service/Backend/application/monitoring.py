from __future__ import annotations

from typing import Any

# Check if prometheus_client is available without overwriting class names
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        REGISTRY,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def _metric(metric_type: Any, name: str, documentation: str, labels: tuple[str, ...]) -> Any:
    # If Prometheus isn't available, this helper won't be called, 
    # but we keep the logic safe just in case.
    try:
        return metric_type(name, documentation, labels)
    except ValueError:
        names_to_collectors = getattr(REGISTRY, "_names_to_collectors", {}) if REGISTRY is not None else {}
        lookup_names = [name]
        if metric_type is Counter and name.endswith("_total"):
            base_name = name.removesuffix("_total")
            lookup_names.extend([base_name, f"{base_name}_total", f"{base_name}_created"])
        for lookup_name in lookup_names:
            existing = names_to_collectors.get(lookup_name)
            if existing is not None:
                return existing
        raise


# Safely initialize globals as either the running metric object or None
if PROMETHEUS_AVAILABLE:
    candle_validation_total = _metric(
        Counter,
        "candle_validation_total",
        "Candle validation decisions.",
        ("status", "valid"),
    )
    candle_feed_delay_seconds = _metric(
        Gauge,
        "candle_feed_delay_seconds",
        "Latest market data feed delay in seconds.",
        ("status",),
    )
    paper_orders_total = _metric(
        Counter,
        "paper_orders_total",
        "Paper order submissions.",
        ("status", "strategy", "symbol"),
    )
    rejected_orders_total = _metric(
        Counter,
        "rejected_orders_total",
        "Rejected order attempts.",
        ("reason", "mode"),
    )
    rejected_signals_total = _metric(
        Counter,
        "rejected_signals_total",
        "Rejected signal decisions.",
        ("strategy", "reason"),
    )
    signal_generation_total = _metric(
        Counter,
        "signal_generation_total",
        "Signal generation attempts.",
        ("strategy", "status"),
    )
    strategy_executions_total = _metric(
        Counter,
        "strategy_executions_total",
        "Strategy execution attempts.",
        ("strategy", "status"),
    )
    strategy_signals_total = _metric(
        Counter,
        "strategy_signals_total",
        "Signals emitted by strategy executions.",
        ("strategy",),
    )
    failed_strategy_executions_total = _metric(
        Counter,
        "failed_strategy_executions_total",
        "Failed strategy executions.",
        ("strategy", "error_type"),
    )
    option_chain_fetch_failures_total = _metric(
        Counter,
        "option_chain_fetch_failures_total",
        "Option-chain provider fetch failures.",
        ("provider", "reason"),
    )
    option_chain_failures_total = _metric(
        Counter,
        "option_chain_failures_total",
        "Option-chain failures.",
        ("provider", "reason"),
    )
    websocket_disconnect_total = _metric(
        Counter,
        "websocket_disconnect_total",
        "WebSocket disconnects.",
        ("reason",),
    )
    market_data_age_seconds = _metric(
        Gauge,
        "market_data_age_seconds",
        "Latest market data age in seconds.",
        ("symbol", "interval"),
    )
    api_request_latency_seconds = _metric(
        Histogram,
        "api_request_latency_seconds",
        "API request latency in seconds.",
        ("method", "path", "status_code"),
    )
    market_data_ticks_total = _metric(
        Counter,
        "market_data_ticks_total",
        "Market data ticks received.",
        ("provider", "symbol"),
    )
    market_data_provider_errors_total = _metric(
        Counter,
        "market_data_provider_errors_total",
        "Market data provider errors.",
        ("provider", "operation"),
    )
    market_data_feed_delay_seconds = _metric(
        Gauge,
        "market_data_feed_delay_seconds",
        "Market data feed delay in seconds.",
        ("provider", "symbol"),
    )
    market_data_cache_hits_total = _metric(
        Counter,
        "market_data_cache_hits_total",
        "Market data cache hits.",
        ("provider", "kind"),
    )
    market_data_cache_misses_total = _metric(
        Counter,
        "market_data_cache_misses_total",
        "Market data cache misses.",
        ("provider", "kind"),
    )
    trading_decisions_total = _metric(
        Counter,
        "trading_decisions_total",
        "Dashboard trading decisions.",
        ("recommendation", "data_status", "blocked"),
    )
    risk_blocks_total = _metric(
        Counter,
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


def observe_option_chain_failure(provider: str, reason: str | None = None) -> None:
    if option_chain_fetch_failures_total is not None:
        option_chain_fetch_failures_total.labels(provider=provider, reason=reason or "unknown").inc()
    if option_chain_failures_total is not None:
        option_chain_failures_total.labels(provider=provider, reason=reason or "unknown").inc()
def observe_market_data_tick(provider: str, symbol: str) -> None:
    """Record a market-data tick."""
    if market_data_ticks_total is not None:
        market_data_ticks_total.labels(
            provider=provider or "unknown",
            symbol=(symbol or "unknown").upper(),
        ).inc()


def observe_market_data_error(provider: str, operation: str) -> None:
    """Record a market-data provider error."""
    if market_data_provider_errors_total is not None:
        market_data_provider_errors_total.labels(
            provider=provider or "unknown",
            operation=operation or "unknown",
        ).inc()


def observe_market_data_delay(
    provider: str,
    symbol: str,
    delay_seconds: float | int | None,
) -> None:
    if market_data_feed_delay_seconds is None or delay_seconds is None:
        return

    market_data_feed_delay_seconds.labels(
        provider=provider or "unknown",
        symbol=(symbol or "unknown").upper(),
    ).set(float(delay_seconds))

def observe_market_data_cache(provider: str, kind: str, hit: bool) -> None:
    """Record cache hit/miss."""
    metric = market_data_cache_hits_total if hit else market_data_cache_misses_total
    if metric is not None:
        metric.labels(
            provider=provider or "unknown",
            kind=kind or "unknown",
        ).inc()
# Paste this at the bottom of Backend/application/monitoring.py

def observe_market_data_age(symbol: str, age_seconds: float) -> None:
    """Proxy fallback wrapper to align old layout mapping."""
    observe_market_data_delay(provider="nse", symbol=symbol, delay_seconds=age_seconds)

def observe_risk_block(strategy: str, rule_triggered: str) -> None:
    """Placeholder to intercept structural routing errors."""
    pass

def observe_trading_decision(strategy: str, action: str, confidence: float) -> None:
    """Placeholder to intercept structural routing errors."""
    pass