#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export APP_DIR
source "${SCRIPT_DIR}/common.sh"

EXPECTED_BRANCH="${EXPECTED_BRANCH:-main}"
SKIP_TESTS=0
SKIP_PULL=0
ROLLBACK_REF=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: deploy-production.sh [--skip-tests] [--skip-pull] [--dry-run] [--rollback <commit-or-tag>]

Deploys QuantGrid from the repository containing this script. Real-money trading
is never enabled by this script. Rollback refuses to run with uncommitted changes.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests) SKIP_TESTS=1 ;;
    --skip-pull) SKIP_PULL=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --rollback)
      shift
      [[ $# -gt 0 ]] || { echo "--rollback requires a commit or tag." >&2; exit 2; }
      ROLLBACK_REF="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
export DRY_RUN

on_error() {
  local line="$1"
  echo "Deployment failed at line ${line}." >&2
  if [[ "${DRY_RUN}" != "1" ]]; then
    sudo systemctl status "${SERVICE_NAME}" --no-pager >&2 || true
    sudo journalctl -u "${SERVICE_NAME}" -n 100 --no-pager >&2 || true
    sudo journalctl -u "${WORKER_SERVICE_NAME}" -n 100 --no-pager >&2 || true
  fi
}
trap 'on_error ${LINENO}' ERR

for command_name in git curl npm sudo; do
  command -v "${command_name}" >/dev/null 2>&1 || { echo "Missing required command: ${command_name}" >&2; exit 1; }
done
require_dir "${APP_DIR}/.git"
require_file "${TRADING_SERVICE_DIR}/.env"
require_file "${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service"
require_file "${APP_DIR}/deploy/systemd/${WORKER_SERVICE_NAME}.service"

cd "${APP_DIR}"
if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
  echo "Deployment refused: unresolved Git conflicts are present." >&2
  exit 1
fi

current_branch="$(git branch --show-current)"
current_commit="$(git rev-parse HEAD)"
dirty=0
if [[ -n "$(git status --porcelain)" ]]; then
  dirty=1
  echo "WARNING: uncommitted changes are present. They will not be deleted." >&2
fi

if [[ -n "${ROLLBACK_REF}" ]]; then
  [[ "${dirty}" == "0" ]] || { echo "Rollback refused while uncommitted changes exist." >&2; exit 1; }
  rollback_commit="$(git rev-parse --verify "${ROLLBACK_REF}^{commit}")" || { echo "Unknown rollback ref: ${ROLLBACK_REF}" >&2; exit 1; }
  log "Rolling back from ${current_commit} to ${rollback_commit}"
  run git checkout --detach "${rollback_commit}"
  SKIP_PULL=1
else
  [[ "${current_branch}" == "${EXPECTED_BRANCH}" ]] || {
    echo "Deployment refused: expected branch ${EXPECTED_BRANCH}, found ${current_branch:-detached}." >&2
    exit 1
  }
  if [[ "${SKIP_PULL}" == "0" && "${dirty}" == "0" ]]; then
    run git fetch origin
    run git merge --ff-only "origin/${EXPECTED_BRANCH}"
  elif [[ "${SKIP_PULL}" == "0" ]]; then
    log "Skipping Git update because the worktree is not clean. Use --skip-pull to acknowledge this state."
  fi
fi

PYTHON="$(python_bin)"
log "Installing backend dependencies"
run "${PYTHON}" -m pip install -r "${TRADING_SERVICE_DIR}/requirements.txt"

log "Validating production environment without printing secrets"
run env QUANTGRID_ENV=production QUANTGRID_ENV_FILE="${TRADING_SERVICE_DIR}/.env" PYTHONPATH="${TRADING_SERVICE_DIR}" \
  "${PYTHON}" -c "from Backend.core.config import validate_security_config; validate_security_config(); print('Production configuration OK')"

log "Compiling backend"
run "${PYTHON}" -m compileall -q "${TRADING_SERVICE_DIR}/Backend"

if [[ "${SKIP_TESTS}" == "0" ]]; then
  log "Running critical release tests"
  run "${PYTHON}" -m pytest -q \
    "${APP_DIR}/tests/test_auth_and_execution_access.py" \
    "${APP_DIR}/tests/test_live_execution_guard.py" \
    "${APP_DIR}/tests/test_broker_status.py" \
    "${APP_DIR}/tests/test_schema_migrations.py" \
    "${APP_DIR}/tests/test_deploy_scripts.py"
else
  log "WARNING: critical tests skipped by operator request"
fi

check_database

log "Building and publishing frontend"
bash "${SCRIPT_DIR}/frontend.sh" deploy
bash "${SCRIPT_DIR}/production_frontend.sh" stop-vite

log "Validating Nginx before restarting services"
run sudo nginx -t

log "Installing current systemd units"
run sudo install -m 0644 "${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
run sudo install -m 0644 "${APP_DIR}/deploy/systemd/${WORKER_SERVICE_NAME}.service" "/etc/systemd/system/${WORKER_SERVICE_NAME}.service"
systemctl_run daemon-reload
systemctl_run enable "${SERVICE_NAME}" "${WORKER_SERVICE_NAME}"
systemctl_run restart "${SERVICE_NAME}" "${WORKER_SERVICE_NAME}"
systemctl_run reload nginx

health_check "${BASE_URL}/health"
if [[ "${DRY_RUN}" != "1" ]]; then
  HEALTH_URL="${BASE_URL}/health" "${PYTHON}" - <<'PY'
import json
import os
from urllib.request import urlopen

with urlopen(os.environ["HEALTH_URL"], timeout=10) as response:
    payload = json.load(response)
if payload.get("database") != "connected":
    raise SystemExit("Health validation failed: database is not connected.")
if payload.get("trading_mode") != "paper":
    raise SystemExit("Health validation failed: production deployment is not in paper mode.")
print(f"Backend health: {payload.get('status')} (database connected, paper mode)")
PY
fi
run curl -fsSI "http://127.0.0.1/" >/dev/null
bash "${SCRIPT_DIR}/production_frontend.sh" check

deployed_commit="$(git rev-parse HEAD)"
log "Deployment complete at ${deployed_commit}"
log "Previous commit was ${current_commit}"
log "Rollback command: bash deploy/scripts/deploy-production.sh --rollback ${current_commit}"
