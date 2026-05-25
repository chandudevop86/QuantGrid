#!/usr/bin/env bash
set -euo pipefail

: "${PRODUCTION_HOST:?Set PRODUCTION_HOST}"
: "${DEPLOY_USER:?Set DEPLOY_USER}"
APP_DIR="${APP_DIR:-/opt/quantgrid}"
REF="${GIT_COMMIT:-main}"

echo "[deploy:production] Deploying ${REF} to ${DEPLOY_USER}@${PRODUCTION_HOST}:${APP_DIR}"
ssh "${DEPLOY_USER}@${PRODUCTION_HOST}" "cd '${APP_DIR}' && git fetch --all --tags && git checkout '${REF}' && git pull --ff-only || true && bash deploy/scripts/deploy_frontend.sh && sudo systemctl restart quantgrid-backend && sudo systemctl status quantgrid-backend --no-pager"
