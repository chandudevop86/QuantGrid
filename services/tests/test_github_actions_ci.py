from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_github_actions_ci_runs_on_push_and_pull_request():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "push:" in workflow
    assert "pull_request:" in workflow


def test_github_actions_ci_runs_backend_quality_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "pip install -r requirements-dev.txt" in workflow
    assert "ruff check services/trading-service services/tests" in workflow
    assert "python scripts/run_test_groups.py --groups 4 --group-timeout 180 --coverage --cov-fail-under 70" in workflow
    assert 'bandit -q -r services/trading-service -x "*/tests/*,*/Testing/*,*/test_*.py" -lll' in workflow
    assert "|| true" not in workflow
    assert "continue-on-error" not in workflow


def test_github_actions_ci_runs_frontend_and_compose_checks():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "npm ci" in workflow
    assert "npm test" in workflow
    assert "npm run test:a11y" in workflow
    assert "npm run build" in workflow
    assert "docker compose -f docker-compose.yml config --quiet" in workflow
    assert "docker compose -f docker-compose.app.yml config --quiet" in workflow


def test_security_workflow_pins_supported_trivy_version():
    workflow = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")

    assert workflow.count("version: v0.74.0") == 3
    assert workflow.count("aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25") == 3


def test_grouped_test_runner_defaults_to_70_percent_coverage():
    runner = (ROOT / "scripts" / "run_test_groups.py").read_text(encoding="utf-8")

    assert 'default=70, help="Coverage threshold for --coverage."' in runner


def test_frontend_ci_runs_tests_before_build():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert workflow.index("run: npm test") < workflow.index("run: npm run build")
    assert workflow.index("run: npm run test:a11y") < workflow.index("run: npm run build")
