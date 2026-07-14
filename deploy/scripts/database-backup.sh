#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-help}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
ENV_FILE="${QUANTGRID_ENV_FILE:-${TRADING_SERVICE_DIR}/.env}"

load_database_url() {
  if [[ -z "${DATABASE_URL:-}" ]]; then
    require_file "${ENV_FILE}"
    set -a
    # The production environment file is operator-controlled and must be mode 0600.
    source "${ENV_FILE}"
    set +a
  fi
  [[ -n "${DATABASE_URL:-}" ]] || { echo "DATABASE_URL is not configured." >&2; exit 1; }
}

case "${ACTION}" in
  backup)
    load_database_url
    command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump is not installed." >&2; exit 1; }
    install -d -m 0700 "${BACKUP_DIR}"
    backup_file="${2:-${BACKUP_DIR}/quantgrid-$(date -u +%Y%m%dT%H%M%SZ).dump}"
    umask 077
    pg_dump --format=custom --no-owner --no-acl --file="${backup_file}" "${DATABASE_URL}"
    pg_restore --list "${backup_file}" >/dev/null
    sha256sum "${backup_file}" >"${backup_file}.sha256"
    echo "Backup created and verified: ${backup_file}"
    ;;
  verify)
    backup_file="${2:?Usage: $0 verify <backup.dump>}"
    command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is not installed." >&2; exit 1; }
    [[ -f "${backup_file}" ]] || { echo "Backup not found: ${backup_file}" >&2; exit 1; }
    [[ -f "${backup_file}.sha256" ]] && sha256sum --check "${backup_file}.sha256"
    pg_restore --list "${backup_file}" >/dev/null
    echo "Backup archive is readable: ${backup_file}"
    ;;
  restore)
    backup_file="${2:?Usage: $0 restore <backup.dump>}"
    [[ "${ALLOW_DATABASE_RESTORE:-}" == "YES" ]] || {
      echo "Restore refused. Set ALLOW_DATABASE_RESTORE=YES and provide RESTORE_DATABASE_URL." >&2
      exit 1
    }
    [[ -n "${RESTORE_DATABASE_URL:-}" ]] || { echo "RESTORE_DATABASE_URL is required." >&2; exit 1; }
    [[ -f "${backup_file}" ]] || { echo "Backup not found: ${backup_file}" >&2; exit 1; }
    command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is not installed." >&2; exit 1; }
    pg_restore --exit-on-error --no-owner --no-acl --clean --if-exists --dbname="${RESTORE_DATABASE_URL}" "${backup_file}"
    echo "Restore completed. Run database.sh check against the restored target."
    ;;
  *)
    echo "Usage: $0 {backup [file]|verify <file>|restore <file>}" >&2
    exit 2
    ;;
esac
