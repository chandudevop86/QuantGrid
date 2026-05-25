#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
BASE_URL="${BASE_URL%/}"

echo "[smoke] Checking ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health" >/dev/null

echo "[smoke] Checking ${BASE_URL}/metrics"
curl -fsS "${BASE_URL}/metrics" >/dev/null

echo "[smoke] Smoke test passed for ${BASE_URL}"
