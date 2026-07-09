#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/QuantGrid}"
SERVICE_NAME="${SERVICE_NAME:-quantgrid-backend}"
WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-quantgrid-worker}"
FRONTEND_DIR="${FRONTEND_DIR:-${APP_DIR}/apps/frontend}"
TRADING_SERVICE_DIR="${TRADING_SERVICE_DIR:-${APP_DIR}/services/trading-service}"
WEB_ROOT="${WEB_ROOT:-/var/www/quantgrid}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

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
  log "Checking ${url}"
  run curl -fsS "${url}"
}

systemctl_run() {
  run sudo systemctl "$@"
}
