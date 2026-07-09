#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

check_database
bash "${SCRIPT_DIR}/backend.sh" restart
bash "${SCRIPT_DIR}/scheduler.sh" restart
health_check "${BASE_URL}/health"
