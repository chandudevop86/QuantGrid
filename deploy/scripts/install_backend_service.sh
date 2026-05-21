#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/QuantGrid}"
SERVICE_NAME="${SERVICE_NAME:-quantgrid-backend}"
SERVICE_FILE="${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service"
ENV_FILE="${APP_DIR}/services/trading-service/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy services/trading-service/.env.example to .env and set real values first." >&2
  exit 1
fi

sudo cp "${SERVICE_FILE}" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl status "${SERVICE_NAME}" --no-pager
