#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-check}"
REDIS_CONTAINER_NAME="${REDIS_CONTAINER_NAME:-quantgrid-redis}"

compose_v2_available() {
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

start_standalone_redis() {
  if docker inspect "${REDIS_CONTAINER_NAME}" >/dev/null 2>&1; then
    run docker start "${REDIS_CONTAINER_NAME}"
    return
  fi
  run docker run -d \
    --name "${REDIS_CONTAINER_NAME}" \
    --restart unless-stopped \
    -p 127.0.0.1:6379:6379 \
    redis:7-alpine
}

case "${ACTION}" in
  start)
    cd "${APP_DIR}"
    if compose_v2_available; then
      compose_run -f docker-compose.yml up -d redis
    else
      log "Compose v2 unavailable; starting isolated Redis container"
      start_standalone_redis
    fi
    ;;
  check)
    if command -v redis-cli >/dev/null 2>&1; then
      run redis-cli -u "${REDIS_URL:-redis://127.0.0.1:6379/0}" ping
    elif docker inspect "${REDIS_CONTAINER_NAME}" >/dev/null 2>&1; then
      run docker exec "${REDIS_CONTAINER_NAME}" redis-cli ping
    else
      health_check "${BASE_URL}/health"
    fi
    ;;
  status)
    cd "${APP_DIR}"
    if compose_v2_available; then
      compose_run -f docker-compose.yml ps redis
    else
      run docker ps -a --filter "name=^/${REDIS_CONTAINER_NAME}$"
    fi
    ;;
  *)
    echo "Usage: $0 {start|check|status}" >&2
    exit 2
    ;;
esac
