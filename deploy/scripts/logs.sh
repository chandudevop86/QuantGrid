#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

TARGET="${1:-backend}"

case "${TARGET}" in
  backend)
    run sudo journalctl -u "${SERVICE_NAME}" -n "${LINES:-200}" --no-pager
    ;;
  scheduler|worker)
    run sudo journalctl -u "${WORKER_SERVICE_NAME}" -n "${LINES:-200}" --no-pager
    ;;
  nginx)
    run sudo journalctl -u nginx -n "${LINES:-200}" --no-pager
    ;;
  *)
    echo "Usage: $0 {backend|scheduler|worker|nginx}" >&2
    exit 2
    ;;
esac
