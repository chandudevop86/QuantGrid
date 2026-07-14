#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
cd "$APP_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Docker Compose is not installed." >&2
  exit 1
fi

for compose_file in docker-compose.yml docker-compose.app.yml; do
  [[ -f "$compose_file" ]] || continue
  "${COMPOSE[@]}" -f "$compose_file" config --quiet
  echo "Validated $compose_file without rendering interpolated values."
done
