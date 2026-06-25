# QuantGrid Beta Readiness

## Runtime Configuration

Set these values in the backend environment:

```bash
QUANTGRID_ENV=production
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/quantgrid
REDIS_URL=redis://redis:6379/0
QUANTGRID_AUTH_SECRET=<stable secret with at least 32 characters>
CORS_ALLOWED_ORIGINS=https://your-frontend.example
QUANTGRID_ENABLE_LIVE_TRADING=false
```

Do not enable live trading until broker credentials, risk limits, and market-data provider settings are configured.

## Redis And WebSocket

Redis is validated at startup and reported in `/health` and `/dashboard/operations`.
When Redis is healthy, WebSocket broadcasts are published through Redis. If Redis is missing or unavailable, QuantGrid falls back to in-process WebSocket broadcasts so the platform remains usable in local and degraded modes.

The production WebSocket endpoint is:

```text
/ws
```

Nginx must pass `Upgrade` and `Connection: upgrade` headers for `/ws`; see `deploy/nginx/quantgrid.conf`.

## Option Chain

The option-chain APIs return a synthetic fallback whenever the live NSE provider fails. Frontend pages must show:

```text
Using Synthetic Option Chain Data
```

Fallback responses include:

```json
{
  "spot": 22500,
  "expiry": "YYYY-MM-DD",
  "atm": 22500,
  "pcr": 1.0,
  "max_pain": 22500,
  "support": 22450,
  "resistance": 22550,
  "signal": "NEUTRAL"
}
```

## Signals And Strategies

Use `GET /api/signals` or `GET /api/signals/latest`. Both routes are authenticated and return an empty payload instead of a frontend-blocking failure when candles are unavailable.

Strategy execution metrics are exported through `/metrics`:

```text
strategy_executions_total
signal_generation_total
rejected_signals_total
```

## Backtesting

Use:

```text
GET /api/strategies/{strategy}/backtest
```

Responses include `total_trades`, `win_rate`, `pnl`, `sharpe_ratio`, `max_drawdown`, and `expectancy`.

## Trade Journal

The journal API is:

```text
GET /api/trade-journal
POST /api/trade-journal
```

For SQLite legacy stores, run `scripts/db/002_beta_trade_journal.sql` if the table does not already exist. SQLAlchemy-backed deployments create the table at startup.

## Monitoring

Prometheus metrics are available at:

```text
GET /metrics
```

Beta dashboard metrics include:

```text
strategy_executions_total
signal_generation_total
rejected_signals_total
websocket_disconnect_total
option_chain_failures_total
market_data_age_seconds
```

## Kubernetes

Use `deploy/kubernetes/quantgrid.yaml` as the backend baseline. It includes startup, readiness, and liveness probes against `/health`.

Before applying it, create:

```bash
kubectl create secret generic quantgrid-secrets \
  --from-literal=database-url='<DATABASE_URL>' \
  --from-literal=redis-url='<REDIS_URL>' \
  --from-literal=auth-secret='<QUANTGRID_AUTH_SECRET>'

kubectl create configmap quantgrid-config \
  --from-literal=cors-allowed-origins='https://your-frontend.example'
```
