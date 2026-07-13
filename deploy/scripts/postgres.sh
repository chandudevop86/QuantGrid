#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-check}"

case "${ACTION}" in
  start)
    require_dir "${APP_DIR}"
    if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
      echo "Set POSTGRES_PASSWORD before starting local Postgres." >&2
      exit 1
    fi
    cd "${APP_DIR}"
    compose_run -f docker-compose.yml up -d postgres
    ;;
  check)
    check_database
    ;;
  status)
    cd "${APP_DIR}"
    compose_run -f docker-compose.yml ps postgres
    ;;
  *)
    echo "Usage: $0 {start|check|status}" >&2
    exit 2
    ;;
esac
