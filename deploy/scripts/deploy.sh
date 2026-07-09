#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

log "Starting QuantGrid deployment"
check_database
bash "${SCRIPT_DIR}/frontend.sh" deploy
bash "${SCRIPT_DIR}/production_frontend.sh" stop-vite
bash "${SCRIPT_DIR}/backend.sh" restart
bash "${SCRIPT_DIR}/scheduler.sh" restart
bash "${SCRIPT_DIR}/nginx.sh" reload
bash "${SCRIPT_DIR}/production_frontend.sh" check
health_check "${BASE_URL}/health"
log "Deployment complete"
