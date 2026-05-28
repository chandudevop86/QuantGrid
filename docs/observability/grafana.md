# Grafana Dashboards and Alerts

QuantGrid exposes Prometheus metrics at:

```text
GET /metrics
```

Configure Prometheus, Grafana Agent, or Amazon Managed Service for Prometheus to scrape the production backend. Use the dashboard panels and alert rules below as the minimum production observability pack.

## Metrics

| Metric | Type | Labels | Use |
| --- | --- | --- | --- |
| `api_request_latency_seconds` | Histogram | `method`, `path`, `status_code` | API latency and 5xx rate |
| `candle_feed_delay_seconds` | Gauge | `status` | Market feed freshness |
| `candle_validation_total` | Counter | `status`, `valid` | Candle validation pass/fail rate |
| `paper_orders_total` | Counter | `status`, `strategy`, `symbol` | Paper execution volume |
| `rejected_orders_total` | Counter | `reason`, `mode` | Rejected order spikes |
| `signal_generation_total` | Counter | `strategy`, `status` | Strategy signal activity |

## Dashboard Panels

### API Latency

Use p95 latency by route:

```promql
histogram_quantile(
  0.95,
  sum by (le, path, method) (
    rate(api_request_latency_seconds_bucket[5m])
  )
)
```

Add a companion request-rate panel:

```promql
sum by (path, method, status_code) (
  rate(api_request_latency_seconds_count[5m])
)
```

### API 5xx Rate

```promql
sum(rate(api_request_latency_seconds_count{status_code=~"5.."}[5m]))
```

### Market Feed Freshness

```promql
max by (status) (candle_feed_delay_seconds)
```

Use thresholds:

| Color | Threshold |
| --- | --- |
| Green | `<= 120s` |
| Yellow | `> 120s` |
| Red | `> 300s` |

### Candle Validation

Validation decisions:

```promql
sum by (status, valid) (
  rate(candle_validation_total[5m])
)
```

Failure ratio:

```promql
sum(rate(candle_validation_total{valid="false"}[5m]))
/
clamp_min(sum(rate(candle_validation_total[5m])), 1)
```

### Paper Orders

```promql
sum by (status, strategy, symbol) (
  increase(paper_orders_total[1h])
)
```

### Rejected Orders

```promql
sum by (mode, reason) (
  increase(rejected_orders_total[15m])
)
```

## Alert Rules

Create these as Grafana-managed alert rules or Prometheus alerting rules.

### QuantGridAPIDown

Use Prometheus `up` if the backend is scraped directly:

```promql
up{job="quantgrid-backend"} == 0
```

Condition:

```text
For: 2m
Severity: critical
```

### QuantGridHigh5xxRate

```promql
sum(rate(api_request_latency_seconds_count{status_code=~"5.."}[5m])) > 0.05
```

Condition:

```text
For: 5m
Severity: critical
```

For low-traffic environments, also add an absolute count alert:

```promql
sum(increase(api_request_latency_seconds_count{status_code=~"5.."}[5m])) >= 5
```

### QuantGridStaleMarketFeed

```promql
max(candle_feed_delay_seconds) > 300
```

Condition:

```text
For: 2m
Severity: critical during market hours
```

Warning rule:

```promql
max(candle_feed_delay_seconds) > 120
```

Condition:

```text
For: 5m
Severity: warning
```

### QuantGridRejectedOrderSpike

```promql
sum(increase(rejected_orders_total[5m])) >= 5
```

Condition:

```text
For: 1m
Severity: warning for paper, critical for live
```

Break down by mode and reason in annotations:

```promql
sum by (mode, reason) (increase(rejected_orders_total[5m]))
```

### QuantGridRedisDisconnected

If Redis exporter is installed:

```promql
redis_up == 0
```

If Redis is only visible through dashboard health, export that check as a synthetic probe and alert on:

```promql
probe_success{job="quantgrid-redis-health"} == 0
```

Condition:

```text
For: 2m
Severity: critical
```

## Alert Annotations

Each alert should include:

```yaml
summary: "QuantGrid {{ $labels.alertname }} in production"
description: "Current value {{ $values.A }} exceeded threshold. Check backend logs, /health, /metrics, Redis, and market data ingestion."
runbook_url: "https://github.com/<org>/<repo>/blob/main/docs/oncall-runbook.md"
dashboard_url: "<grafana-dashboard-url>"
```

## Minimum Dashboard Layout

1. API health and p95 latency
2. API 5xx rate by route
3. Market feed delay and candle validation status
4. Paper orders by strategy and symbol
5. Rejected orders by mode and reason
6. Redis health and WebSocket fallback status

Keep the dashboard filtered by `environment`, `service`, and `instance` labels when those labels are available from the scraper.
