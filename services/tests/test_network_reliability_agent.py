from Backend.application.monitoring.network_reliability_agent import assess_network_reliability


def _metrics():
    return dict(api_p95_ms=100, api_p99_ms=300, http_5xx_ratio=0,
                db_pool_used=2, db_pool_capacity=10, redis_queue_depth=0,
                worker_oldest_job_seconds=0, dhan_feed_age_seconds=2,
                tls_days_remaining=90)


def test_healthy_network():
    result = assess_network_reliability(**_metrics())
    assert result["status"] == "healthy"
    assert result["market_data_usable"]


def test_stale_feed_disables_market_data():
    result = assess_network_reliability(**{**_metrics(), "dhan_feed_age_seconds": 60})
    assert "stale_dhan_market_feed" in result["alerts"]
    assert not result["market_data_usable"]


def test_db_pool_saturation_disables_market_data():
    result = assess_network_reliability(**{**_metrics(), "db_pool_used": 9})
    assert "database_pool_saturation" in result["alerts"]
    assert not result["market_data_usable"]


def test_invalid_metrics_fail_closed():
    assert not assess_network_reliability(**{**_metrics(), "db_pool_capacity": 0})["market_data_usable"]
    assert not assess_network_reliability(**{**_metrics(), "api_p95_ms": float("nan")})["market_data_usable"]
