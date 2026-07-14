# QuantGrid

QuantGrid is a trading dashboard with a React/Vite frontend and a FastAPI trading-service for trading signals, execution safety, market data validation, live analysis jobs, auth, audit logs, and websocket updates.

The official production architecture is a modular monolith:

`Nginx -> React frontend -> FastAPI trading-service -> Postgres/Redis`

Placeholder services and service-extraction experiments live in `experimental/` and are not production systems.

## Project Layout

- `apps/frontend/` - React dashboard built with Vite.
- `services/trading-service/` - Main FastAPI trading API.
- `experimental/` - Non-production service experiments and placeholders.
- `infra/` - Kafka topic initialization helpers.
- `deploy/` - systemd, Nginx, and deployment scripts.
- `docs/` - Architecture, operations, release, security, and process docs.
- `scripts/` - CI/CD and project automation scripts.
- `tests/` - Backend test suite and category directories.

## Frontend

```bash
cd apps/frontend
npm install
npm run build
npm run dev
```

The frontend reads `VITE_API_BASE_URL` or `VITE_API_URL`. In Vite dev on port
`5173`, set `VITE_API_URL` when the backend is not available through `/api`.
For production Nginx, build with `VITE_API_URL=/api` and `VITE_WS_URL=/ws`
so browser login posts to the reverse proxy instead of the user machine's localhost.
## Trading API

```bash
cd services/trading-service
pip install -r requirements.txt
uvicorn Backend.presentation.api.main:app --reload --host 0.0.0.0 --port 8000
```

For persistent server configuration, copy `services/trading-service/.env.example`
to `services/trading-service/.env` and set real values there. The backend loads
that file automatically, and OS environment variables still take precedence.
This prevents accidental restarts with a temporary auth secret.

Live analysis jobs are stored in SQLite, queued by the REST API, executed by a
worker, and published to Redis channel `updates`. The API starts a background
task after creating a job, and you can also run the durable worker loop as a
separate process:

```bash
cd services/trading-service
python -m Backend.application.live_analysis_worker
```

Set `CORS_ALLOWED_ORIGINS` as a comma-separated list in production. Set
`JOB_STORE_DB_FILE` if the SQLite job database should live outside the default
`services/trading-service/data/dashboard_jobs.sqlite3` path.
Live market prices and candles are stored in SQLite at
`services/trading-service/Backend/data/market_data.sqlite3`; set
`MARKET_DATA_DB_FILE` to move this database.

Authentication is token based. Set `QUANTGRID_AUTH_SECRET` to a strong secret
with at least 32 characters before starting the API. Users are stored in the
configured database table `users`, with security events in `audit_logs`.

Local-only seed users are allowed only when both `QUANTGRID_ENV=local` and
`QUANTGRID_ALLOW_DEV_SEED_USERS=true` are set. Provide local seed users with
`QUANTGRID_USERS=admin:AdminPass1!:admin`. Seed passwords must satisfy the
password policy and must not be known defaults such as `admin123`. In local
seed mode, explicitly configured seed users are reconciled on startup, so an
existing local `admin` password is updated to match `QUANTGRID_USERS`.

Production must set `DATABASE_URL=postgresql+psycopg://...`; production startup
fails if `DATABASE_URL` is missing or points to SQLite.

For production database setup, start Postgres with a persistent Docker volume:

```bash
cd ~/QuantGrid
export POSTGRES_PASSWORD='replace-with-a-strong-postgres-password'
bash deploy/scripts/start_postgres.sh
```

Then use `services/trading-service/.env.production.example` as the server
template:

```bash
cd ~/QuantGrid/services/trading-service
cp .env.production.example .env
nano .env
python -m Backend.tools.check_database
```

The check command creates missing auth/audit tables and prints the active
database dialect without exposing the database password.

Market data fails closed by default. Set `ALLOW_SAMPLE_MARKET_DATA=true` only for
offline demos where generated fallback prices and candles are acceptable.

Execution is paper-only unless live trading is explicitly enabled. The current
API rejects live execution because no live broker order adapter is wired into the
execution endpoint yet.

Broker login can be checked while execution remains paper-only. For Dhan, set:

```bash
QUANTGRID_BROKER_PROVIDER=dhan
QUANTGRID_BROKER_CLIENT_ID=your_dhan_client_id
QUANTGRID_BROKER_ACCESS_TOKEN=your_dhan_access_token
QUANTGRID_ENABLE_LIVE_TRADING=false
```

Then call `GET /broker/status` or view the dashboard Broker Login card. This
validates the Dhan token with Dhan's profile API but does not enable real-money
orders.

Paper execution applies broker-style sizing safeguards before simulation:

```bash
QUANTGRID_LOT_SIZE_NIFTY=65
QUANTGRID_MAX_ORDER_NOTIONAL=1000000
QUANTGRID_MARGIN_MULTIPLIER=1
QUANTGRID_ROUND_DOWN_TO_LOT=true
MIN_SIGNAL_SCORE=7
SIGNAL_MAX_AGE_MINUTES=5
QUANTGRID_CANDLE_WARNING_SECONDS=120
QUANTGRID_CANDLE_REJECT_SECONDS=300
QUANTGRID_FEED_DELAY_TOLERANCE_SECONDS=60
QUANTGRID_MAX_MISSING_CANDLES=2
QUANTGRID_NSE_HOLIDAYS=2026-01-26,2026-03-03,2026-03-31,2026-04-03,2026-04-14,2026-05-01,2026-08-15,2026-10-02,2026-11-09,2026-12-25
QUANTGRID_MARKET_CACHE_TTL_SECONDS=10
REDIS_URL=redis://localhost:6379/0
QUANTGRID_MAX_DAILY_LOSS=3000
QUANTGRID_MAX_TRADES_PER_DAY=3
QUANTGRID_MAX_CONSECUTIVE_LOSSES=2
```

Signals below one lot or above the configured margin/notional limit are rejected
as `no_trade`.

Professional paper-trading safeguards separate signals into active, rejected,
and stale buckets. Stale signals older than the latest candle by more than two
minutes are not actionable, scores below `MIN_SIGNAL_SCORE` are rejected as
`LOW_SCORE`, and choppy/MTF-conflicting signals are blocked before paper
execution.

Market data defaults to `QUANTGRID_MARKET_DATA_PROVIDER=yahoo`. Yahoo data is
not trading-grade and should not be used for live execution.

## Institutional Dashboard

Phase 1 adds a first-pass market command center at `/institutional` backed by
`GET /institutional/dashboard`. It combines configured institutional inputs
with live option-chain metrics when a provider returns real rows. Missing feeds
stay unavailable instead of being replaced with synthetic FII/DII, macro, PCR,
or max-pain values.

Optional configured inputs:

```bash
FII_CASH_FLOW=150.5
DII_CASH_FLOW=-20
FII_INDEX_FUTURES=12500
GIFT_NIFTY=24510
INDIA_VIX=13.4
USDINR=83.25
CRUDE_OIL=84.7
GOLD=2350
GLOBAL_INDICES_JSON='[{"label":"S&P 500","value":6200,"change_pct":0.4}]'
```

Option-chain derived PCR, max pain, highest call OI, highest put OI, and OI
change are shown only when live provider data is available.

## Backtesting Engine

Phase 2 adds a dedicated backtesting workspace at `/backtesting` backed by:

- `POST /modules/backtesting` for one strategy replay.
- `POST /modules/backtesting/comparison` for multi-strategy ranking.

The backtest response includes CAGR, total return, win rate, max drawdown,
Sharpe ratio, profit factor, total trades, average profit, average loss,
average P/L, and an equity curve. The comparison endpoint ranks strategies by
Sharpe, net P&L, and drawdown using the same paper-only replay engine.

## Portfolio & Risk Engine

Phase 3 adds a portfolio-risk workspace at `/risk` backed by
`GET /risk/dashboard`. The dashboard aggregates daily, weekly, and monthly
P&L, fixed-risk sizing, ATR-based sizing, daily loss limit, max open trades,
max trades per day, exposure limit, and open-position risk.

Optional risk inputs:

```bash
QUANTGRID_CAPITAL=100000
QUANTGRID_RISK_PER_TRADE_PCT=1
QUANTGRID_MAX_DAILY_LOSS=3000
QUANTGRID_MAX_OPEN_POSITIONS=3
QUANTGRID_MAX_TRADES_PER_DAY=3
QUANTGRID_MAX_EXPOSURE=150000
QUANTGRID_ATR_FALLBACK=25
```

The risk dashboard is read-only. Execution remains protected by the existing
paper/live separation, risk gate, kill switch, and broker guardrails.

## AI Market Copilot

Phase 4 adds an explanatory Market Copilot at `/copilot` backed by
`GET /trading/copilot/market`. It summarizes the current F&O narrative, explains
the scenario, lists bullish and bearish evidence, shows invalidation, confidence,
market narrative, and what changed since the previous refresh.

The Copilot is deterministic and guardrailed. It does not place trades, enable
live execution, or issue blind buy/sell calls. Execution still requires strategy
validation, risk approval, and the configured paper/live mode.

The candle validator normalizes timestamps to `Asia/Kolkata`, understands the
NSE regular session, and disables stale-candle rejection after close, on
weekends, and on configured holidays. During live market hours, candles warn
after `QUANTGRID_CANDLE_WARNING_SECONDS` and reject only after
`QUANTGRID_CANDLE_REJECT_SECONDS + QUANTGRID_FEED_DELAY_TOLERANCE_SECONDS`.
Use `GET /market/validation/NIFTY?interval=1m` to inspect the structured feed
status, delay, missing-candle count, and human-readable diagnostics.

## Websocket Updates

Websocket updates are served by the production trading service at `/ws`. Set
`REDIS_URL` for the trading API if Redis is not running at
`redis://localhost:6379/0`.

## Alerts

QuantGrid can send operational alerts for queued/completed analysis jobs and
paper execution outcomes. Alerts are optional and disabled automatically when no
channel is configured.

Telegram:

```bash
export TELEGRAM_BOT_TOKEN=123456:bot-token
export TELEGRAM_CHAT_ID=123456789
```

Slack:

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Email:

```bash
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_USERNAME=alerts@example.com
export SMTP_PASSWORD=app-password
export SMTP_FROM=alerts@example.com
export SMTP_TO=admin@example.com,ops@example.com
```

Set `QUANTGRID_ALERTS_ENABLED=false` to disable all alert delivery.

## Systemd

The backend should run as a systemd service instead of a terminal process.
Example service files live in `deploy/systemd/`, and helper scripts live in
`deploy/scripts/`.

```bash
cd ~/QuantGrid
git pull origin main

cd services/trading-service
cp .env.example .env
nano .env

cd ~/QuantGrid
bash deploy/scripts/install_backend_service.sh
sudo systemctl status quantgrid-backend
```

The frontend is served as static files through Nginx in production, so it does
not need a long-running Vite service.

## HTTPS Reverse Proxy

Example Nginx configs live in `deploy/nginx/`. They serve the built frontend
from `/var/www/quantgrid`, proxy `/api/` to the backend on `127.0.0.1:8000`, and
proxy `/ws` for websocket job updates.

Typical EC2 setup:

```bash
cd ~/QuantGrid
git pull origin main

bash deploy/scripts/deploy_frontend.sh
bash deploy/scripts/install_nginx.sh http
```

Issue the TLS certificate, then switch to the HTTPS config:

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d chandudevopai.shop -d www.chandudevopai.shop
bash deploy/scripts/install_nginx.sh https
```

Useful routes:

- `GET /health`
- `GET /dashboard/summary`
- `GET /dashboard/live-analysis/jobs`
- `POST /dashboard/live-analysis/jobs`
- `GET /trading/strategies`
- `POST /trading/signals`
- `POST /execution/order`
- `GET /market/price`
- `GET /market/candles/{symbol}`
- `GET /market/stored/{symbol}`
- `GET /market/store/status`
- `GET /broker/status`
- `GET /api/signals/latest`
- `GET /api/trades/paper`
- `GET /api/risk/status`
- `GET /api/strategies/{strategy}/backtest`

## Infrastructure

```bash
docker compose -f docker-compose.yml up -d
```

This starts Kafka, Zookeeper, Redis, and Postgres for the local services.
Set `POSTGRES_PASSWORD` before starting the stack.

AWS 3-tier Terraform lives in `infra/terraform/aws`; see `infra/terraform/aws/README.md` before planning or applying infrastructure.



