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

Live analysis jobs are queued by the REST API, executed by a background worker
task in the trading service, and published to Redis channel `updates`.

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

## Infrastructure

```bash
docker compose -f Docker-compose.yml up -d
```

This starts Kafka, Zookeeper, Redis, and Postgres for the local services.
