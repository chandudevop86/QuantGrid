#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-status}"
SERVICE_FILE="${APP_DIR}/deploy/systemd/${WORKER_SERVICE_NAME}.service"
ENV_FILE="${TRADING_SERVICE_DIR}/.env"

case "${ACTION}" in
  install)
    require_file "${ENV_FILE}"
    check_database
    ensure_systemd_service "${WORKER_SERVICE_NAME}" "${SERVICE_FILE}"
    systemctl_run restart "${WORKER_SERVICE_NAME}"
    systemctl_run status "${WORKER_SERVICE_NAME}" --no-pager
    ;;
  restart)
    require_file "${ENV_FILE}"
    ensure_systemd_service "${WORKER_SERVICE_NAME}" "${SERVICE_FILE}"
    check_database
    systemctl_run restart "${WORKER_SERVICE_NAME}"
    ;;
  status)
    systemctl_run status "${WORKER_SERVICE_NAME}" --no-pager
    ;;
  logs)
    run sudo journalctl -u "${WORKER_SERVICE_NAME}" -n "${LINES:-200}" --no-pager
    ;;
  *)
    echo "Usage: $0 {install|restart|status|logs}" >&2
    exit 2
    ;;
esac
