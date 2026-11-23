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
    "$(python_bin)" "${APP_DIR}/scripts/postgres_archive.py" backup "${backup_file}"
    pg_restore --list "${backup_file}" >/dev/null
    sha256sum "${backup_file}" >"${backup_file}.sha256"
    "$(python_bin)" "${APP_DIR}/scripts/option_ledger_backup.py" backup "${backup_file}" \
      "${QUANTGRID_OPTION_PAPER_LEDGER:-${TRADING_SERVICE_DIR}/Backend/data/option_paper.sqlite3}"
    echo "Backup created and verified: ${backup_file}"
    ;;
  verify)
    backup_file="${2:?Usage: $0 verify <backup.dump>}"
    command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is not installed." >&2; exit 1; }
    [[ -f "${backup_file}" ]] || { echo "Backup not found: ${backup_file}" >&2; exit 1; }
    [[ -f "${backup_file}.sha256" ]] && sha256sum --check "${backup_file}.sha256"
    pg_restore --list "${backup_file}" >/dev/null
    "$(python_bin)" "${APP_DIR}/scripts/option_ledger_backup.py" verify "${backup_file}"
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
    "$(python_bin)" "${APP_DIR}/scripts/option_ledger_backup.py" restore-check "${backup_file}" \
      ${RESTORE_OPTION_PAPER_LEDGER:+"${RESTORE_OPTION_PAPER_LEDGER}"}
    "$(python_bin)" "${APP_DIR}/scripts/postgres_archive.py" restore "${backup_file}"
    "$(python_bin)" "${APP_DIR}/scripts/option_ledger_backup.py" restore "${backup_file}" \
      ${RESTORE_OPTION_PAPER_LEDGER:+"${RESTORE_OPTION_PAPER_LEDGER}"}
    echo "Restore completed. Run database.sh check against the restored target."
    ;;
  *)
    echo "Usage: $0 {backup [file]|verify <file>|restore <file>}" >&2
    exit 2
    ;;
esac
