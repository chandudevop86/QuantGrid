from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_test_group_runner_is_used_by_ci_and_jenkins():
    runner = (ROOT / "scripts" / "run_test_groups.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    jenkinsfile = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")

    assert "subprocess.run" in runner
    assert "timeout=args.group_timeout" in runner
    assert '--pattern' in runner
    assert "stdout=subprocess.PIPE" in runner
    assert 'encoding="utf-8"' in runner
    assert "verbose=args.verbose" in runner
    assert "Print stdout for passing pytest groups" in runner
    assert "Pytest group {index} passed." in runner
    assert 'PYTHONIOENCODING", "utf-8"' in runner
    assert "--cov-append" in runner
    assert '"coverage", "report"' in runner
    assert "--test-timeout" in runner
    assert "--timeout-method=thread" in runner
    assert "python scripts/run_test_groups.py" in workflow
    assert "python scripts/run_test_groups.py" in jenkinsfile


def test_dev_requirements_include_lint_and_timeout_tools():
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "ruff" in requirements
    assert "pytest-timeout" in requirements


def test_runner_discovers_nested_strategy_regressions():
    from scripts import run_test_groups

    paths = run_test_groups._test_files("test_*.py")
    assert any(path.name == "test_smc_safety_regressions.py" for path in paths)
    assert any(path.name == "test_mtfa_strategy.py" for path in paths)
    assert run_test_groups._relative_test_arg(
        "services/tests/strategy/test_smc_safety_regressions.py"
    ) == "strategy/test_smc_safety_regressions.py"
