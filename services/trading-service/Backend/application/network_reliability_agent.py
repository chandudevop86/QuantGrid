"""Read-only QuantGrid network and service SLO evaluator.

Consumes trusted monitoring measurements; does not probe third-party systems,
change firewall rules, restart services, or submit broker orders.
"""
from __future__ import annotations

import math


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def assess_network_reliability(*, api_p95_ms, api_p99_ms, http_5xx_ratio,
                               db_pool_used, db_pool_capacity, redis_queue_depth,
                               worker_oldest_job_seconds, dhan_feed_age_seconds,
                               tls_days_remaining):
    values = (api_p95_ms, api_p99_ms, http_5xx_ratio, db_pool_used,
              db_pool_capacity, redis_queue_depth, worker_oldest_job_seconds,
              dhan_feed_age_seconds, tls_days_remaining)
    if (not all(_number(x) for x in values) or not 0 < db_pool_capacity
            or db_pool_used > db_pool_capacity or http_5xx_ratio > 1
            or api_p99_ms < api_p95_ms):
        return {"status": "unknown", "market_data_usable": False,
                "alerts": ["missing or inconsistent monitoring data"]}
    alerts = []
    if api_p95_ms > 500 or api_p99_ms > 1500:
        alerts.append("api_latency_slo_breached")
    if http_5xx_ratio > 0.01:
        alerts.append("api_error_budget_breached")
    if db_pool_used / db_pool_capacity >= 0.8:
        alerts.append("database_pool_saturation")
    if redis_queue_depth > 100 or worker_oldest_job_seconds > 30:
        alerts.append("worker_backlog")
    if dhan_feed_age_seconds > 15:
        alerts.append("stale_dhan_market_feed")
    if tls_days_remaining < 14:
        alerts.append("tls_certificate_expiry")
    return {
        "status": "degraded" if alerts else "healthy",
        "market_data_usable": dhan_feed_age_seconds <= 15 and http_5xx_ratio <= 0.01
                              and db_pool_used / db_pool_capacity < 0.8,
        "alerts": alerts,
        "db_pool_utilization": round(db_pool_used / db_pool_capacity, 4),
        "thresholds": {"p95_ms": 500, "p99_ms": 1500, "error_ratio": 0.01,
                       "db_pool_utilization": 0.8, "feed_age_seconds": 15},
    }
