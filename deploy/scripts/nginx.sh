#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-test}"
MODE="${2:-http}"
SITE_NAME="${SITE_NAME:-quantgrid}"

case "${ACTION}" in
  install)
    if [[ "${MODE}" == "https" ]]; then
      SOURCE="${APP_DIR}/deploy/nginx/quantgrid.conf"
    else
      SOURCE="${APP_DIR}/deploy/nginx/quantgrid-http.conf"
    fi
    require_file "${SOURCE}"
    run sudo mkdir -p /var/www/certbot
    run sudo cp "${SOURCE}" "/etc/nginx/sites-available/${SITE_NAME}"
    run sudo ln -sf "/etc/nginx/sites-available/${SITE_NAME}" "/etc/nginx/sites-enabled/${SITE_NAME}"
    run sudo nginx -t
    run sudo systemctl reload nginx
    ;;
  reload)
    run sudo nginx -t
    run sudo systemctl reload nginx
    ;;
  test)
    run sudo nginx -t
    ;;
  *)
    echo "Usage: $0 {install|reload|test} [http|https]" >&2
    exit 2
    ;;
esac
