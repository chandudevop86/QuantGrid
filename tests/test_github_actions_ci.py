from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_github_actions_ci_runs_on_push_and_pull_request():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "push:" in workflow
    assert "pull_request:" in workflow


def test_github_actions_ci_runs_backend_quality_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "pip install -r requirements-dev.txt" in workflow
    assert "ruff check services/trading-service tests" in workflow
    assert "python scripts/run_test_groups.py --groups 4 --group-timeout 180 --coverage --cov-fail-under 45" in workflow
    assert 'bandit -q -r services/trading-service -x "*/tests/*"' in workflow
    assert "|| true" not in workflow
    assert "continue-on-error" not in workflow


def test_github_actions_ci_runs_frontend_and_compose_checks():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "npm ci" in workflow
    assert "npm run build" in workflow
    assert "docker compose -f docker-compose.yml config" in workflow
    assert "docker compose -f docker-compose.app.yml config" in workflow
