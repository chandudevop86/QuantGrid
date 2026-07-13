#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-check}"

case "${ACTION}" in
  check|init|migrate)
    check_database
    ;;
  *)
    echo "Usage: $0 {check|init|migrate}" >&2
    echo "Use postgres.sh for database service start/status operations." >&2
    exit 2
    ;;
esac
