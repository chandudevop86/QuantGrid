#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-check}"

case "${ACTION}" in
  start)
    cd "${APP_DIR}"
    compose_run -f docker-compose.yml up -d redis
    ;;
  check)
    if command -v redis-cli >/dev/null 2>&1; then
      run redis-cli -u "${REDIS_URL:-redis://127.0.0.1:6379/0}" ping
    else
      health_check "${BASE_URL}/health"
    fi
    ;;
  status)
    cd "${APP_DIR}"
    compose_run -f docker-compose.yml ps redis
    ;;
  *)
    echo "Usage: $0 {start|check|status}" >&2
    exit 2
    ;;
esac
