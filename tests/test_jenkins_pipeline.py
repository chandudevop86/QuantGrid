from pathlib import Path


def test_jenkins_pytest_stage_fails_pipeline_on_test_failure():
    jenkinsfile = Path(__file__).resolve().parents[1] / "Jenkinsfile"
    text = jenkinsfile.read_text(encoding="utf-8")

    assert "python -m pytest tests" in text
    assert "set -eu" in text
    assert "returnStatus" not in text
    assert "pytest tests --cov=services/trading-service/Backend --cov-report=term-missing --cov-fail-under=45 || true" not in text


def test_jenkins_requires_manual_approval_after_staging_before_production():
    jenkinsfile = Path(__file__).resolve().parents[1] / "Jenkinsfile"
    text = jenkinsfile.read_text(encoding="utf-8")

    staging_stage = text.index("stage('Deploy to staging')")
    approval_stage = text.index("stage('Manual approval before production')")
    production_stage = text.index("stage('Deploy production')")

    assert staging_stage < approval_stage < production_stage
    assert "sh 'bash scripts/jenkins/deploy_staging.sh'" in text
    assert "input message: 'Deploy QuantGrid to production?'" in text
    assert "sh 'bash scripts/jenkins/deploy_production.sh'" in text


def test_jenkins_rolls_back_when_production_smoke_fails():
    jenkinsfile = Path(__file__).resolve().parents[1] / "Jenkinsfile"
    text = jenkinsfile.read_text(encoding="utf-8")

    production_stage = text.index("stage('Deploy production')")
    production_started_flag = text.index("env.PRODUCTION_DEPLOY_STARTED = 'true'")
    smoke_stage = text.index("stage('Post-deploy smoke test')")
    rollback_step = text.index('sh \'bash scripts/jenkins/rollback.sh "${ROLLBACK_REF:-HEAD~1}" production\'')

    assert "PRODUCTION_DEPLOY_STARTED = 'false'" in text
    assert production_stage < production_started_flag < smoke_stage < rollback_step
    assert "env.BRANCH_NAME == 'main' && env.PRODUCTION_DEPLOY_STARTED == 'true'" in text
    assert 'sh \'bash scripts/jenkins/smoke_test.sh "${PRODUCTION_URL}"\'' in text
