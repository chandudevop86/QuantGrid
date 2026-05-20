# QuantGrid

QuantGrid is a trading dashboard and service playground with a React/Vite frontend and FastAPI-based backend services for trading signals, execution, market data, live analysis jobs, and websocket updates.

## Project Layout

- `frontend/` - React dashboard built with Vite.
- `services/trading-service/` - Main FastAPI trading API.
- `services/strategy-service/` - Minimal strategy signal service.
- `services/market-data-service/` - Placeholder market data service.
- `services/auth-service/` - Placeholder auth service.
- `gateway/` - FastAPI proxy gateway.
- `engine/` - Kafka order execution worker.
- `websocket/` - Redis-backed websocket broadcaster.
- `infra/` - Kafka topic initialization helpers.

## Frontend

```bash
cd frontend
npm install
npm run build
npm run dev
```

The frontend reads `VITE_API_BASE_URL` and defaults to `http://localhost:8000`.

## Trading API

```bash
cd services/trading-service
pip install -r requirements.txt
uvicorn Backend.presentation.api.main:app --reload --host 0.0.0.0 --port 8000
```

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
`QUANTGRID_USERS=username:StrongPass1!:admin`. Do not use known default
passwords.

Production must set `DATABASE_URL=postgresql+psycopg://...`; production startup
fails if `DATABASE_URL` is missing or points to SQLite.

Market data fails closed by default. Set `ALLOW_SAMPLE_MARKET_DATA=true` only for
offline demos where generated fallback prices and candles are acceptable.

Execution is paper-only unless live trading is explicitly enabled. The current
API rejects live execution because no live broker order adapter is wired into the
execution endpoint yet.

Market data defaults to `QUANTGRID_MARKET_DATA_PROVIDER=yahoo`. Yahoo data is
not trading-grade and should not be used for live execution.

## Websocket Updates

```bash
cd websocket
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8005
```

Set `REDIS_URL` for both the trading API and websocket service if Redis is not
running at `redis://localhost:6379/0`.

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

## Infrastructure

```bash
docker compose -f Docker-compose.yml up -d
```

This starts Kafka, Zookeeper, Redis, and Postgres for the local services.
Set `POSTGRES_PASSWORD` before starting the stack.
