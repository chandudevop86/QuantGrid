#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/QuantGrid}"
SERVICE_NAME="${SERVICE_NAME:-quantgrid-backend}"
WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-quantgrid-worker}"
FRONTEND_DIR="${FRONTEND_DIR:-${APP_DIR}/apps/frontend}"
TRADING_SERVICE_DIR="${TRADING_SERVICE_DIR:-${APP_DIR}/services/trading-service}"
WEB_ROOT="${WEB_ROOT:-/var/www/quantgrid}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-2}"

log() {
  printf '[quantgrid] %s\n' "$*"
}

run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

compose_run() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    run docker compose "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    run docker-compose "$@"
    return
  fi
  echo "Docker Compose is unavailable. Install the docker-compose-plugin or docker-compose." >&2
  return 127
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

require_dir() {
  if [[ ! -d "$1" ]]; then
    echo "Missing required directory: $1" >&2
    exit 1
  fi
}

python_bin() {
  if [[ -x "${PYTHON_BIN:-}" ]]; then
    echo "${PYTHON_BIN}"
  elif [[ -x /root/venv/bin/python ]]; then
    echo /root/venv/bin/python
  else
    command -v python3
  fi
}

check_database() {
  require_dir "${TRADING_SERVICE_DIR}"
  log "Checking database schema and connectivity"
  cd "${TRADING_SERVICE_DIR}"
  run "$(python_bin)" -m Backend.tools.check_database
}

health_check() {
  local url="${1:-${BASE_URL}/health}"
  local attempts="${2:-${HEALTH_RETRIES}}"
  local sleep_seconds="${3:-${HEALTH_SLEEP_SECONDS}}"
  local attempt
  log "Checking ${url}"
  for attempt in $(seq 1 "${attempts}"); do
    if run curl -fsS "${url}" >/dev/null; then
      log "Health check passed: ${url}"
      return 0
    fi
    if [[ "${attempt}" -lt "${attempts}" ]]; then
      log "Backend not ready yet (${attempt}/${attempts}); waiting ${sleep_seconds}s"
      sleep "${sleep_seconds}"
    fi
  done

  echo "Backend health check failed after ${attempts} attempts: ${url}" >&2
  echo "Service status:" >&2
  sudo systemctl status "${SERVICE_NAME}" --no-pager >&2 || true
  echo "Recent backend logs:" >&2
  sudo journalctl -u "${SERVICE_NAME}" -n "${HEALTH_LOG_LINES:-120}" --no-pager >&2 || true
  return 1
}

systemctl_run() {
  run sudo systemctl "$@"
}

systemd_unit_exists() {
  local service="$1"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    return 1
  fi
  sudo systemctl list-unit-files "${service}.service" --no-legend 2>/dev/null | grep -q "^${service}.service"
}

ensure_systemd_service() {
  local service="$1"
  local service_file="$2"
  require_file "${service_file}"
  if systemd_unit_exists "${service}"; then
    return 0
  fi
  log "Installing missing systemd unit: ${service}.service"
  run sudo cp "${service_file}" "/etc/systemd/system/${service}.service"
  systemctl_run daemon-reload
  systemctl_run enable "${service}"
}
