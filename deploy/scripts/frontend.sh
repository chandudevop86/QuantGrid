#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-build}"

case "${ACTION}" in
  build)
    require_dir "${FRONTEND_DIR}"
    cd "${FRONTEND_DIR}"
    run npm ci
    run npm run build
    ;;
  deploy)
    bash "${SCRIPT_DIR}/frontend.sh" build
    run sudo mkdir -p "${WEB_ROOT}"
    run sudo rsync -a --delete "${FRONTEND_DIR}/dist/" "${WEB_ROOT}/"
    run sudo chown -R www-data:www-data "${WEB_ROOT}"
    log "Frontend deployed to ${WEB_ROOT}"
    ;;
  *)
    echo "Usage: $0 {build|deploy}" >&2
    exit 2
    ;;
esac
