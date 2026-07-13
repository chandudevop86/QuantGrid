from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_app_compose_includes_full_local_stack_with_healthchecks():
    compose = (ROOT / "docker-compose.app.yml").read_text(encoding="utf-8")

    for service in ("backend:", "worker:", "frontend:", "postgres:", "redis:", "migrate:"):
        assert service in compose

    assert compose.count("healthcheck:") >= 4
    assert "docker/backend.Dockerfile" in compose
    assert '"Backend.application.worker"' in compose
    assert 'command: ["python", "-m", "Backend.tools.check_database"]' in compose
    assert "condition: service_completed_successfully" in compose
    assert "docker/frontend.Dockerfile" in compose
    assert "VITE_API_URL: ${VITE_API_URL:-/api}" in compose
    assert "VITE_API_BASE_URL: ${VITE_API_BASE_URL:-/api}" in compose
    assert "VITE_WS_URL: ${VITE_WS_URL:-/ws}" in compose
    assert "postgresql+psycopg://quant:local-quantgrid-postgres@postgres:5432/quantgrid" in compose
    assert "redis://redis:6379/0" in compose
    assert "QUANTGRID_AUTH_SECRET:?Set QUANTGRID_AUTH_SECRET" in compose
    assert "ALLOW_SAMPLE_MARKET_DATA:-false" in compose
    assert "QUANTGRID_ALLOW_DEV_SEED_USERS:-false" in compose
    assert "http://127.0.0.1:8000/health" in compose
    assert '"127.0.0.1:5432:5432"' in compose
    assert '"127.0.0.1:6379:6379"' in compose
    assert '"127.0.0.1:5173:80"' in compose


def test_frontend_container_uses_compiled_nginx_build():
    dockerfile = (ROOT / "docker" / "frontend.Dockerfile").read_text(encoding="utf-8")

    assert "ARG VITE_API_URL=/api" in dockerfile
    assert "ARG VITE_API_BASE_URL=/api" in dockerfile
    assert "ARG VITE_WS_URL=/ws" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "FROM nginx:" in dockerfile
    assert 'CMD ["nginx", "-g", "daemon off;"]' in dockerfile
    assert "npm\", \"run\", \"dev" not in dockerfile


def test_app_stack_documents_safe_env_defaults():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "QUANTGRID_ENV=local" in env_example
    assert "QUANTGRID_AUTH_SECRET=local-dev-auth-secret-at-least-32-characters" in env_example
    assert "DATABASE_URL=postgresql+psycopg://quant:local-quantgrid-postgres@postgres:5432/quantgrid" in env_example
    assert "REDIS_URL=redis://redis:6379/0" in env_example
    assert "VITE_API_URL=/api" in env_example
    assert "VITE_WS_URL=/ws" in env_example
