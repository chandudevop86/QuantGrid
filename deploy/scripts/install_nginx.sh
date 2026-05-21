#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/QuantGrid}"
SITE_NAME="${SITE_NAME:-quantgrid}"
MODE="${1:-http}"

if [[ "${MODE}" == "https" ]]; then
  SOURCE="${APP_DIR}/deploy/nginx/quantgrid.conf"
else
  SOURCE="${APP_DIR}/deploy/nginx/quantgrid-http.conf"
fi

sudo mkdir -p /var/www/certbot
sudo cp "${SOURCE}" "/etc/nginx/sites-available/${SITE_NAME}"
sudo ln -sf "/etc/nginx/sites-available/${SITE_NAME}" "/etc/nginx/sites-enabled/${SITE_NAME}"
sudo nginx -t
sudo systemctl reload nginx

echo "Installed Nginx ${MODE} config for ${SITE_NAME}."
