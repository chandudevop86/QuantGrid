#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/QuantGrid}"

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "Set POSTGRES_PASSWORD before starting Postgres." >&2
  exit 1
fi

cd "${APP_DIR}"
docker compose -f Docker-compose.yml up -d postgres
docker compose -f Docker-compose.yml ps postgres
