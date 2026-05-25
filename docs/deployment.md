# Deployment Guide

## Local Setup

```bash
python -m pip install -r services/trading-service/requirements.txt
cd apps/frontend && npm ci && npm run build
cd ../..
uvicorn Backend.presentation.api.main:app --app-dir services/trading-service --reload --port 8000
```

## Staging Setup

- Use Postgres, not SQLite.
- Set `QUANTGRID_ENV=staging`.
- Set `QUANTGRID_AUTH_SECRET` from a secret manager.
- Set `CORS_ALLOWED_ORIGINS` to the staging frontend origin.
- Keep `QUANTGRID_ENABLE_LIVE_TRADING=false`.

## Production Setup

- Use Postgres with persistent backups.
- Set `QUANTGRID_ENV=production`.
- Set `DATABASE_URL=postgresql+psycopg://...`.
- Set `QUANTGRID_AUTH_SECRET` to a strong secret.
- Set explicit `CORS_ALLOWED_ORIGINS`.
- Keep live trading disabled unless broker execution has been formally approved.

## Systemd

```bash
bash deploy/scripts/install_backend_service.sh
sudo systemctl status quantgrid-backend --no-pager
sudo journalctl -u quantgrid-backend -n 200 --no-pager
```

## Nginx

```bash
bash deploy/scripts/deploy_frontend.sh
bash deploy/scripts/install_nginx.sh https
sudo nginx -t
sudo systemctl reload nginx
```

## Database Check

```bash
cd services/trading-service
python -m Backend.tools.check_database
```

## Smoke Tests

```bash
bash scripts/jenkins/smoke_test.sh https://your-domain.example/api
```

## Rollback

```bash
bash scripts/jenkins/rollback.sh v0.1.0 production
```
