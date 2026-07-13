#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "Set POSTGRES_PASSWORD before starting Postgres." >&2
  exit 1
fi

cd "${APP_DIR}"
compose_run -f docker-compose.yml up -d postgres
compose_run -f docker-compose.yml ps postgres
