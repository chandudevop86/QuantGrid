from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "deploy" / "scripts"


REQUIRED_SCRIPTS = {
    "common.sh",
    "backend.sh",
    "frontend.sh",
    "database.sh",
    "postgres.sh",
    "redis.sh",
    "nginx.sh",
    "scheduler.sh",
    "deploy.sh",
    "restart.sh",
    "logs.sh",
    "production_frontend.sh",
}


def _text(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_devops_automation_scripts_exist_and_use_safe_shell_mode():
    existing = {path.name for path in SCRIPTS.glob("*.sh")}

    assert REQUIRED_SCRIPTS <= existing
    for name in REQUIRED_SCRIPTS:
        text = _text(name)
        assert text.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in text


def test_service_scripts_source_common_helpers():
    for name in REQUIRED_SCRIPTS - {"common.sh"}:
        text = _text(name)
        assert 'source "${SCRIPT_DIR}/common.sh"' in text


def test_deploy_and_restart_validate_database_before_backend_restart():
    deploy = _text("deploy.sh")
    restart = _text("restart.sh")

    assert deploy.index("check_database") < deploy.index('bash "${SCRIPT_DIR}/backend.sh" restart')
    assert restart.index("check_database") < restart.index('bash "${SCRIPT_DIR}/backend.sh" restart')


def test_database_script_exposes_expected_check_command_without_duplicate_schema_logic():
    database = _text("database.sh")

    assert "check|init|migrate)" in database
    assert "Usage: $0 {check|init|migrate}" in database
    assert "check_database" in database
    assert "Backend.tools.check_database" not in database
    assert "CREATE TABLE" not in database
    assert "Use postgres.sh for database service start/status operations." in database


def test_health_check_waits_and_prints_backend_diagnostics():
    common = _text("common.sh")

    assert "HEALTH_RETRIES" in common
    assert "Backend not ready yet" in common
    assert "Backend health check failed after" in common
    assert 'systemctl status "${SERVICE_NAME}"' in common
    assert 'journalctl -u "${SERVICE_NAME}"' in common


def test_compose_scripts_support_plugin_and_standalone_commands():
    common = _text("common.sh")
    redis = _text("redis.sh")
    postgres = _text("postgres.sh")

    assert "docker compose version" in common
    assert "command -v docker-compose" in common
    assert 'run docker compose "$@"' in common
    assert 'run docker-compose "$@"' in common
    assert "compose_run -f docker-compose.yml" in redis
    assert "compose_run -f docker-compose.yml" in postgres


def test_redis_compose_is_not_blocked_by_unrelated_postgres_interpolation():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    postgres = _text("postgres.sh")

    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-}" in compose
    assert '${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD' not in compose
    assert 'if [[ -z "${POSTGRES_PASSWORD:-}" ]]' in postgres
    assert "Set POSTGRES_PASSWORD before starting local Postgres." in postgres


def test_redis_script_avoids_legacy_compose_containerconfig_failure():
    redis = _text("redis.sh")

    assert "compose_v2_available" in redis
    assert "start_standalone_redis" in redis
    assert '--name "${REDIS_CONTAINER_NAME}"' in redis
    assert "--restart unless-stopped" in redis
    assert "-p 127.0.0.1:6379:6379" in redis
    assert "redis:7-alpine" in redis
    assert 'docker exec "${REDIS_CONTAINER_NAME}" redis-cli ping' in redis
    assert "--remove-orphans" not in redis


def test_systemd_production_env_uses_host_redis_address():
    production_env = (ROOT / "services" / "trading-service" / ".env.production.example").read_text(encoding="utf-8")
    backend_unit = (ROOT / "deploy" / "systemd" / "quantgrid-backend.service").read_text(encoding="utf-8")
    worker_unit = (ROOT / "deploy" / "systemd" / "quantgrid-worker.service").read_text(encoding="utf-8")

    assert "REDIS_URL=redis://127.0.0.1:6379/0" in production_env
    assert "REDIS_URL=redis://redis:6379/0" not in production_env
    assert "EnvironmentFile=/root/QuantGrid/services/trading-service/.env" in backend_unit
    assert "EnvironmentFile=/root/QuantGrid/services/trading-service/.env" in worker_unit


def test_restart_installs_missing_systemd_units_before_restart():
    common = _text("common.sh")
    backend = _text("backend.sh")
    scheduler = _text("scheduler.sh")

    assert "ensure_systemd_service()" in common
    assert "systemctl list-unit-files" in common
    assert 'ensure_systemd_service "${SERVICE_NAME}" "${SERVICE_FILE}"' in backend
    assert 'ensure_systemd_service "${WORKER_SERVICE_NAME}" "${SERVICE_FILE}"' in scheduler
    assert backend.index('ensure_systemd_service "${SERVICE_NAME}" "${SERVICE_FILE}"') < backend.index('systemctl_run restart "${SERVICE_NAME}"')
    assert scheduler.index('ensure_systemd_service "${WORKER_SERVICE_NAME}" "${SERVICE_FILE}"') < scheduler.index('systemctl_run restart "${WORKER_SERVICE_NAME}"')


def test_dry_run_does_not_call_real_systemd_unit_lookup():
    common = _text("common.sh")

    assert 'if [[ "${DRY_RUN:-0}" == "1" ]]; then' in common
    assert common.index('if [[ "${DRY_RUN:-0}" == "1" ]]; then', common.index("systemd_unit_exists()")) < common.index("sudo systemctl list-unit-files")


def test_production_frontend_guard_blocks_vite_and_requires_static_bundle():
    deploy = _text("deploy.sh")
    restart = _text("restart.sh")
    guard = _text("production_frontend.sh")

    assert 'bash "${SCRIPT_DIR}/production_frontend.sh" stop-vite' in deploy
    assert 'bash "${SCRIPT_DIR}/production_frontend.sh" check' in deploy
    assert 'bash "${SCRIPT_DIR}/production_frontend.sh" check' in restart
    assert "/@vite/client" in guard
    assert "/src/main" in guard
    assert '"/assets/"' in guard
    assert "Production must use Nginx static assets, not Vite." in guard


def test_scripts_do_not_hardcode_secrets_or_live_trading_enablement():
    combined = "\n".join(_text(name) for name in REQUIRED_SCRIPTS)

    forbidden = [
        "BROKER_LIVE_ENABLED=true",
        "QUANTGRID_ENABLE_LIVE_TRADING=true",
        "access-token:",
        "password=",
        "secret=",
    ]
    for marker in forbidden:
        assert marker not in combined
