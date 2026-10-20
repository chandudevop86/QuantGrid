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


def test_canonical_trading_api_entrypoint_is_unambiguous():
    root = ROOT
    assert not (root / "services" / "trading-service" / "main.py").exists()

    systemd = (
        root / "deploy" / "systemd" / "quantgrid-backend.service"
    ).read_text(encoding="utf-8")
    dockerfile = (root / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    canonical = "Backend.presentation.api.main:app"
    assert canonical in systemd
    assert canonical in dockerfile


def test_ci_runs_frontend_playwright_smoke_tests():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "npx playwright install --with-deps chromium" in workflow
    assert "npm run test:e2e" in workflow

    build_index = workflow.index("npm run build")
    browser_index = workflow.index("npx playwright install --with-deps chromium")
    e2e_index = workflow.index("npm run test:e2e")
    assert build_index < browser_index < e2e_index


def test_github_actions_use_node24_capable_first_party_actions():
    workflows = [
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "workflows" / "security.yml",
        ROOT / ".github" / "workflows" / "codeql.yml",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in workflows)

    assert "actions/checkout@v4" not in combined
    assert "actions/setup-python@v5" not in combined
    assert "actions/setup-node@v4" not in combined

    assert "actions/checkout@v7" in combined
    assert "actions/setup-python@v7" in combined
    assert "actions/setup-node@v7" in combined

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'node-version: "24"' in ci


def test_backend_ci_enforces_risk_critical_module_coverage():
    runner = (ROOT / "scripts" / "run_test_groups.py").read_text(encoding="utf-8")
    checker = (ROOT / "scripts" / "check_critical_coverage.py").read_text(encoding="utf-8")

    assert "check_critical_coverage.py" in runner
    assert '"80"' in runner

    for module in (
        "broker_reconciliation.py",
        "execution_guardrails.py",
        "risk_gate.py",
        "trade_exit_engine.py",
    ):
        assert module in checker
