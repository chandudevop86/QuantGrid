#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-check}"
VITE_PORT="${VITE_PORT:-5174}"

vite_pids() {
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -f "vite.*(--port[[:space:]]+${VITE_PORT}|:${VITE_PORT}|--host)" || true
  fi
}

vite_port_open() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :${VITE_PORT} )" | grep -q ":${VITE_PORT}"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${VITE_PORT}" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v netstat >/dev/null 2>&1; then
    netstat -ltn | grep -q ":${VITE_PORT}[[:space:]]"
  else
    return 1
  fi
}

check_static_bundle() {
  require_file "${WEB_ROOT}/index.html"
  if grep -q "/@vite/client\\|/src/main" "${WEB_ROOT}/index.html"; then
    echo "Production frontend is serving Vite dev assets from ${WEB_ROOT}/index.html." >&2
    echo "Run: bash deploy/scripts/frontend.sh deploy" >&2
    exit 1
  fi
  if ! grep -q "/assets/" "${WEB_ROOT}/index.html"; then
    echo "Production frontend index.html does not reference built /assets/ files." >&2
    echo "Run: bash deploy/scripts/frontend.sh deploy" >&2
    exit 1
  fi
}

check_no_vite() {
  if [[ "${ALLOW_VITE_IN_PROD:-0}" == "1" ]]; then
    log "Skipping Vite production guard because ALLOW_VITE_IN_PROD=1"
    return 0
  fi
  if vite_port_open; then
    echo "Vite dev server is listening on port ${VITE_PORT}. Production must use Nginx static assets, not Vite." >&2
    echo "Run: bash deploy/scripts/production_frontend.sh stop-vite" >&2
    exit 1
  fi
}

stop_vite() {
  local pids
  pids="$(vite_pids | tr '\n' ' ' | xargs || true)"
  if [[ -z "${pids}" ]]; then
    log "No Vite dev server processes found"
    return 0
  fi
  log "Stopping Vite dev server processes: ${pids}"
  run kill ${pids}
}

case "${ACTION}" in
  check)
    check_static_bundle
    check_no_vite
    log "Production frontend is serving built static assets from ${WEB_ROOT}"
    ;;
  stop-vite)
    stop_vite
    ;;
  *)
    echo "Usage: $0 {check|stop-vite}" >&2
    exit 2
    ;;
esac
