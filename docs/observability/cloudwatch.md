# CloudWatch Monitoring

QuantGrid production should publish backend logs to CloudWatch Logs and scrape `/metrics` into a metrics backend. Use CloudWatch alarms for service reachability and log-derived failures, and keep Grafana alerts as the primary Prometheus metric alerting layer.

## Required Signals

| Signal | Source | Purpose |
| --- | --- | --- |
| API health | Synthetic check against `/health` | Detect backend down or unreachable |
| 5xx rate | Backend structured logs or ALB metrics | Detect API errors before users report them |
| Market feed freshness | `candle_feed_delay_seconds` | Detect stale candles that can block live signals |
| Rejected orders | `rejected_orders_total` or `order_rejected` logs | Detect execution/risk failures |
| Redis connectivity | `/dashboard/summary` health payload or Redis service metrics | Detect cache/pub-sub outage |

## API Down Alarm

Create a CloudWatch Synthetics canary or Route 53 health check for:

```text
https://<production-domain>/health
```

Alarm when:

```text
SuccessPercent < 100 for 2 consecutive periods of 1 minute
```

Page immediately. `/health` must return HTTP 200 with a small JSON body. Any timeout, DNS failure, TLS failure, or non-2xx response is unhealthy.

## High 5xx Rate

If QuantGrid is behind an Application Load Balancer, alarm on:

```text
AWS/ApplicationELB HTTPCode_Target_5XX_Count
```

Suggested threshold:

```text
Sum >= 5 over 5 minutes
```

If using backend logs only, create a metric filter on the API log group:

```text
{ $.logger = "quantgrid.api" && $.status_code >= 500 }
```

Emit metric:

```text
Namespace: QuantGrid/Backend
MetricName: Api5xxCount
Value: 1
```

Alarm when:

```text
Sum(Api5xxCount) >= 5 for 1 datapoint over 5 minutes
```

## Stale Market Feed

Prometheus exposes:

```text
candle_feed_delay_seconds{status="<market-status>"}
```

If this is shipped to CloudWatch through the CloudWatch Agent Prometheus scraper or Amazon Managed Service for Prometheus, create an alarm equivalent to:

```text
max(candle_feed_delay_seconds) > 300
```

Suggested severities:

| Severity | Condition |
| --- | --- |
| Warning | Feed delay above 120 seconds for 5 minutes |
| Critical | Feed delay above 300 seconds for 2 minutes during market hours |

Do not page for stale feed outside market hours unless after-market analysis is expected to run fresh ingestion.

## Rejected Order Spike

Preferred metric:

```text
rejected_orders_total{mode="<paper|live>",reason="<reason>"}
```

Alert equivalent:

```text
increase(rejected_orders_total[5m]) >= 5
```

If using logs, create a metric filter for execution rejection events:

```text
{ $.event = "order_rejected" || $.event = "signal_rejected" }
```

Emit metric:

```text
Namespace: QuantGrid/Execution
MetricName: RejectedOrderCount
Value: 1
```

Page only for live mode. Route paper-mode spikes to the trading/dev channel for investigation.

## Redis Disconnected

Redis failures show up in dashboard health and can break WebSocket/pub-sub behavior. Monitor one of:

```text
/dashboard/summary -> health.redis.connected == true
```

or managed Redis metrics such as:

```text
AWS/ElastiCache CurrConnections
AWS/ElastiCache EngineCPUUtilization
AWS/ElastiCache Evictions
```

Alarm when the dashboard health check reports Redis disconnected for 2 consecutive minutes. Also alert on Redis process/service down if Redis is self-hosted.

## Incident Routing

| Alert | Route |
| --- | --- |
| API down | Page primary operator |
| High 5xx rate | Page backend/on-call |
| Stale market feed | Page trading operator during market hours |
| Rejected live order spike | Page trading + backend |
| Redis disconnected | Page platform/on-call |

Every alert should include the service, environment, runbook link, current value, threshold, and dashboard URL.
