from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_app_compose_includes_full_local_stack_with_healthchecks():
    compose = (ROOT / "docker-compose.app.yml").read_text(encoding="utf-8")

    for service in ("backend:", "frontend:", "postgres:", "redis:"):
        assert service in compose

    assert compose.count("healthcheck:") >= 4
    assert "docker/backend.Dockerfile" in compose
    assert "docker/frontend.Dockerfile" in compose
    assert "postgresql+psycopg://quant:local-quantgrid-postgres@postgres:5432/quantgrid" in compose
    assert "redis://redis:6379/0" in compose
    assert "http://127.0.0.1:8000/health" in compose


def test_app_stack_documents_safe_env_defaults():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "QUANTGRID_ENV=local" in env_example
    assert "QUANTGRID_AUTH_SECRET=local-dev-auth-secret-at-least-32-characters" in env_example
    assert "DATABASE_URL=postgresql+psycopg://quant:local-quantgrid-postgres@postgres:5432/quantgrid" in env_example
    assert "REDIS_URL=redis://redis:6379/0" in env_example
    assert "VITE_API_URL=http://localhost:8000" in env_example
    assert "VITE_WS_URL=ws://localhost:8000/ws" in env_example
