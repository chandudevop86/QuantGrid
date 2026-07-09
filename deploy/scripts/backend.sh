#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-status}"
SERVICE_FILE="${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service"
ENV_FILE="${TRADING_SERVICE_DIR}/.env"

case "${ACTION}" in
  install)
    require_file "${ENV_FILE}"
    require_file "${SERVICE_FILE}"
    check_database
    run sudo cp "${SERVICE_FILE}" "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl_run daemon-reload
    systemctl_run enable "${SERVICE_NAME}"
    systemctl_run restart "${SERVICE_NAME}"
    systemctl_run status "${SERVICE_NAME}" --no-pager
    ;;
  restart)
    check_database
    systemctl_run restart "${SERVICE_NAME}"
    health_check "${BASE_URL}/health"
    ;;
  status)
    systemctl_run status "${SERVICE_NAME}" --no-pager
    ;;
  logs)
    run sudo journalctl -u "${SERVICE_NAME}" -n "${LINES:-200}" --no-pager
    ;;
  check)
    check_database
    health_check "${BASE_URL}/health"
    ;;
  *)
    echo "Usage: $0 {install|restart|status|logs|check}" >&2
    exit 2
    ;;
esac
