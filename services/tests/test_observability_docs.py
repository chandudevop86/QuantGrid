from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cloudwatch_observability_doc_covers_required_alerts():
    text = (ROOT / "docs" / "observability" / "cloudwatch.md").read_text(encoding="utf-8")

    assert "/health" in text
    assert "5xx" in text
    assert "candle_feed_delay_seconds" in text
    assert "rejected_orders_total" in text
    assert "Redis" in text


def test_grafana_observability_doc_covers_alerts_and_dashboard_metrics():
    text = (ROOT / "docs" / "observability" / "grafana.md").read_text(encoding="utf-8")

    assert "QuantGridAPIDown" in text
    assert "QuantGridHigh5xxRate" in text
    assert "QuantGridStaleMarketFeed" in text
    assert "QuantGridRejectedOrderSpike" in text
    assert "QuantGridRedisDisconnected" in text
    assert "api_request_latency_seconds" in text
    assert "paper_orders_total" in text
    assert "rejected_orders_total" in text
    assert "candle_validation_total" in text
