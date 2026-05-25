#!/usr/bin/env bash
set -euo pipefail

: "${STAGING_HOST:?Set STAGING_HOST}"
: "${DEPLOY_USER:?Set DEPLOY_USER}"
APP_DIR="${APP_DIR:-/opt/quantgrid}"
REF="${GIT_COMMIT:-main}"

echo "[deploy:staging] Deploying ${REF} to ${DEPLOY_USER}@${STAGING_HOST}:${APP_DIR}"
ssh "${DEPLOY_USER}@${STAGING_HOST}" "cd '${APP_DIR}' && git fetch --all --tags && git checkout '${REF}' && git pull --ff-only || true && bash deploy/scripts/deploy_frontend.sh && sudo systemctl restart quantgrid-backend && sudo systemctl status quantgrid-backend --no-pager"
