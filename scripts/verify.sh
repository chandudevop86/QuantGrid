#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export QUANTGRID_ENV="${QUANTGRID_ENV:-local}"
export QUANTGRID_AUTH_SECRET="${QUANTGRID_AUTH_SECRET:-ci-secret-value-that-is-long-enough-12345}"
export QUANTGRID_ALLOW_DEV_SEED_USERS="${QUANTGRID_ALLOW_DEV_SEED_USERS:-true}"

py -3.12 -m ruff check services/trading-service tests
py -3.12 -m compileall -q services/trading-service tests
py -3.12 scripts/check_no_secrets.py
py -3.12 scripts/check_production_config.py
py -3.12 scripts/run_test_groups.py --groups 4 --group-timeout 600 --coverage --cov-fail-under 45

(
  cd apps/frontend
  NODE_ENV=development npm ci --include=dev
  NODE_ENV=development npm run build
  NODE_ENV=test npm test -- --reporter=default
)

if command -v docker >/dev/null 2>&1; then
  POSTGRES_PASSWORD=ci-postgres-password docker compose -f docker-compose.yml config --quiet
  docker compose -f docker-compose.app.yml config --quiet
else
  echo "warning: Docker is unavailable; Compose validation was skipped" >&2
fi
