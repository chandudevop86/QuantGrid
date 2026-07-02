from __future__ import annotations

from conftest import admin_headers

from app.security.security_ops_loop import SecurityCheckInput, SecurityStatus, run_security_scan


SECURE_K8S = """
apiVersion: v1
kind: ServiceAccount
metadata:
  name: quantgrid-backend
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: quantgrid-read
rules: []
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: quantgrid-default-deny
spec:
  podSelector: {}
  policyTypes: ["Ingress", "Egress"]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quantgrid-backend
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: quantgrid/backend:test
          securityContext:
            readOnlyRootFilesystem: true
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
"""


SECURE_TERRAFORM = """
resource "aws_lb_listener" "https" {
  port            = 443
  protocol        = "HTTPS"
  certificate_arn = var.alb_certificate_arn
}

terraform {
  backend "s3" {
    encrypt = true
  }
}

resource "aws_db_instance" "main" {
  storage_encrypted       = true
  backup_retention_period = 7
}
"""


SECURE_WORKFLOW = """
jobs:
  security:
    steps:
      - run: gitleaks detect --source .
      - run: pip-audit -r services/trading-service/requirements.txt
      - run: trivy image quantgrid/backend:test
      - run: terraform fmt -check -recursive infra/terraform
      - run: terraform validate
      - run: trivy config infra deploy/kubernetes
      - run: pytest
      - run: echo prometheus grafana alert coverage
"""


def _secure_input(**overrides):
    base = {
        "repo_root": "Z:/does-not-exist",
        "kubernetes_manifests": [SECURE_K8S],
        "dockerfiles": {"backend.Dockerfile": "FROM python:3.12-slim\nUSER 10001\n"},
        "terraform_files": {"main.tf": SECURE_TERRAFORM},
        "workflow_files": {"security.yml": SECURE_WORKFLOW},
        "controls": {
            "waf_enabled": True,
            "api_rate_limiting": True,
            "jwt_validation": True,
            "cors_locked_down": True,
            "api_auth_required": True,
            "audit_logs": True,
        },
    }
    base.update(overrides)
    return SecurityCheckInput(**base)


def _all_findings(result):
    return result.critical_findings + result.warnings


def test_public_database_should_be_critical():
    result = run_security_scan(
        _secure_input(security_group_rules=[{"cidr": "0.0.0.0/0", "from_port": 5432, "to_port": 5432}])
    )

    assert result.overall_status == SecurityStatus.CRITICAL
    assert any("database" in finding.title.lower() and finding.severity == "CRITICAL" for finding in result.critical_findings)


def test_open_ssh_0_0_0_0_should_be_critical():
    result = run_security_scan(
        _secure_input(security_group_rules=[{"cidr": "0.0.0.0/0", "from_port": 22, "to_port": 22}])
    )

    assert result.overall_status == SecurityStatus.CRITICAL
    assert any("admin port" in finding.title.lower() for finding in result.critical_findings)


def test_missing_network_policy_should_be_warning():
    result = run_security_scan(_secure_input(kubernetes_manifests=[SECURE_K8S.replace("kind: NetworkPolicy", "kind: ConfigMap")]))

    assert result.overall_status == SecurityStatus.WARNING
    assert any("networkpolicy" in finding.title.lower() for finding in result.warnings)


def test_missing_resource_limits_should_be_warning():
    result = run_security_scan(_secure_input(kubernetes_manifests=[SECURE_K8S.replace("resources:", "resources_disabled:")]))

    assert result.overall_status == SecurityStatus.WARNING
    assert any("resource limits" in finding.title.lower() for finding in result.warnings)


def test_secure_config_should_pass():
    result = run_security_scan(_secure_input())

    assert result.overall_status == SecurityStatus.SECURE
    assert result.security_score == 100
    assert not _all_findings(result)


def test_security_dashboard_endpoint_returns_cards(app_client):
    response = app_client.get("/security/dashboard", headers=admin_headers(app_client))

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] in {"SECURE", "WARNING", "CRITICAL"}
    assert isinstance(payload["dashboard_cards"], list)
