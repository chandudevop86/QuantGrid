# QuantGrid production release checklist

QuantGrid's EC2 production path is Nginx serving `apps/frontend/dist`, FastAPI
running as `quantgrid-backend`, a `quantgrid-worker` process, PostgreSQL, and
host Redis. Production deployment must remain in paper mode.

## Pre-deployment

```bash
cd ~/QuantGrid
git status
git branch --show-current
git log --oneline -5
cp services/trading-service/.env.production.example services/trading-service/.env
# Edit .env with protected production values, then restrict it:
chmod 600 services/trading-service/.env
bash deploy/scripts/deploy-production.sh --dry-run
```

Do not copy the example over an existing production `.env`.

## Deploy

```bash
cd ~/QuantGrid
bash deploy/scripts/deploy-production.sh
```

Use `--skip-pull` only when the checked-out commit was selected intentionally.
Use `--skip-tests` only during a documented emergency deployment.

## Verify

```bash
git status
git branch --show-current
git log --oneline -5
sudo systemctl status quantgrid-backend --no-pager
sudo systemctl status quantgrid-worker --no-pager
sudo journalctl -u quantgrid-backend -n 100 --no-pager
sudo nginx -t
curl -fsS http://127.0.0.1:8000/health
curl -fsSI http://127.0.0.1/
```

Then verify through the HTTPS UI: login, dashboard load, one NIFTY candle
request, one strategy analysis, one paper order, its audit record, and restart
recovery. Keep `QUANTGRID_ENABLE_LIVE_TRADING=false` and
`BROKER_LIVE_ENABLED=false`.

## Rollback

Use the previous commit printed by the deployment script:

```bash
cd ~/QuantGrid
git status
bash deploy/scripts/deploy-production.sh --rollback <previous-known-good-commit>
```

Rollback refuses a dirty worktree and uses a detached checkout. It does not run
`git reset --hard`, `git clean`, or remove runtime data. Return to the production
branch after the incident is resolved with `git checkout main`.
