#!/usr/bin/env bash
set -euo pipefail

ROLLBACK_REF="${1:?Usage: rollback.sh <git-ref> <staging|production>}"
TARGET="${2:-staging}"
APP_DIR="${APP_DIR:-/opt/quantgrid}"

case "${TARGET}" in
  staging)
    : "${STAGING_HOST:?Set STAGING_HOST}"
    HOST="${STAGING_HOST}"
    ;;
  production)
    : "${PRODUCTION_HOST:?Set PRODUCTION_HOST}"
    HOST="${PRODUCTION_HOST}"
    ;;
  *)
    echo "Unknown rollback target: ${TARGET}" >&2
    exit 2
    ;;
esac

: "${DEPLOY_USER:?Set DEPLOY_USER}"

echo "[rollback:${TARGET}] Rolling back ${HOST} to ${ROLLBACK_REF}"
ssh "${DEPLOY_USER}@${HOST}" "cd '${APP_DIR}' && git fetch --all --tags && git checkout '${ROLLBACK_REF}' && bash deploy/scripts/deploy_frontend.sh && sudo systemctl restart quantgrid-backend && sudo systemctl status quantgrid-backend --no-pager"
