#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/QuantGrid}"
FRONTEND_DIR="${APP_DIR}/frontend"
WEB_ROOT="${WEB_ROOT:-/var/www/quantgrid}"

cd "${FRONTEND_DIR}"

if [[ ! -f ".env.production" && -f ".env.production.example" ]]; then
  cp .env.production.example .env.production
fi

npm install
npm run build

sudo mkdir -p "${WEB_ROOT}"
sudo rsync -a --delete dist/ "${WEB_ROOT}/"
sudo chown -R www-data:www-data "${WEB_ROOT}" 2>/dev/null || true

echo "Frontend deployed to ${WEB_ROOT}."
