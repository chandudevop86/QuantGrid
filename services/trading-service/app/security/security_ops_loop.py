from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SecuritySeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    WARNING = "WARNING"
    INFO = "INFO"


class SecurityStatus(str, Enum):
    SECURE = "SECURE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class SecurityFinding(BaseModel):
    title: str
    severity: SecuritySeverity
    affected_component: str
    evidence: str
    impact: str
    fix_steps: list[str]
    category: str = "general"


class SecurityRecommendation(BaseModel):
    title: str
    priority: SecuritySeverity
    action: str
    affected_component: str


class SecurityDashboardCard(BaseModel):
    name: str
    category: str
    status: SecurityStatus
    score: int
    summary: str
    finding_count: int = 0


class SecurityCheckInput(BaseModel):
    repo_root: str | None = None
    scan_type: str = "full"
    security_group_rules: list[dict[str, Any]] = Field(default_factory=list)
    nacl_rules: list[dict[str, Any]] = Field(default_factory=list)
    kubernetes_manifests: list[str] = Field(default_factory=list)
    dockerfiles: dict[str, str] = Field(default_factory=dict)
    terraform_files: dict[str, str] = Field(default_factory=dict)
    workflow_files: dict[str, str] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    controls: dict[str, bool] = Field(default_factory=dict)
    image_vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)
    dependency_scan: dict[str, Any] = Field(default_factory=dict)


class SecurityScanResult(BaseModel):
    timestamp: str
    overall_status: SecurityStatus
    security_score: int
    critical_findings: list[SecurityFinding]
    warnings: list[SecurityFinding]
    passed_checks: list[str]
    recommended_actions: list[SecurityRecommendation]
    dashboard_summary: str
    dashboard_cards: list[SecurityDashboardCard]
    trend: list[dict[str, Any]] = Field(default_factory=list)


ADMIN_PORTS = {22, 3389, 5432, 6379, 9200, 9300, 9092}
DATABASE_PORTS = {5432, 3306, 1433, 1521, 27017, 6379}
CATEGORY_ORDER = ["network", "api", "kubernetes", "containers", "iam", "database", "devsecops"]


def _service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_repo_root() -> Path:
    return _service_root().parents[1]


def _history_db_file() -> Path:
    configured = os.getenv("SECURITY_SCAN_DB_FILE")
    if configured:
        return Path(configured)
    return _service_root() / "Backend" / "data" / "security_scan_history.sqlite3"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _copy_model(model: SecurityCheckInput, update: dict[str, Any]) -> SecurityCheckInput:
    if hasattr(model, "model_copy"):
        return model.model_copy(update=update)
    return model.copy(update=update)


def _load_default_input(payload: SecurityCheckInput | None) -> SecurityCheckInput:
    data = payload or SecurityCheckInput()
    root = Path(data.repo_root or _default_repo_root())
    if data.kubernetes_manifests or data.dockerfiles or data.terraform_files or data.workflow_files:
        return data

    terraform_dir = root / "infra" / "terraform" / "aws"
    workflow_dir = root / ".github" / "workflows"
    docker_dir = root / "docker"
    kubernetes_dir = root / "deploy" / "kubernetes"
    return _copy_model(
        data,
        {
            "repo_root": str(root),
            "terraform_files": {str(path.relative_to(root)): _read_text(path) for path in terraform_dir.glob("*.tf")},
            "workflow_files": {str(path.relative_to(root)): _read_text(path) for path in workflow_dir.glob("*.yml")},
            "dockerfiles": {str(path.relative_to(root)): _read_text(path) for path in docker_dir.glob("*Dockerfile")},
            "kubernetes_manifests": [_read_text(path) for path in kubernetes_dir.glob("*.yaml")],
        },
    )


def _dump_model(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value.dict()


class _FindingBuilder:
    def __init__(self) -> None:
        self.findings: list[SecurityFinding] = []
        self.passed: list[str] = []

    def pass_check(self, title: str) -> None:
        self.passed.append(title)

    def add(
        self,
        *,
        title: str,
        severity: SecuritySeverity,
        affected_component: str,
        evidence: str,
        impact: str,
        fix_steps: list[str],
        category: str,
    ) -> None:
        self.findings.append(
            SecurityFinding(
                title=title,
                severity=severity,
                affected_component=affected_component,
                evidence=evidence,
                impact=impact,
                fix_steps=fix_steps,
                category=category,
            )
        )


def _port_range(rule: dict[str, Any]) -> set[int]:
    raw_port = rule.get("port") or rule.get("from_port") or rule.get("to_port")
    try:
        from_port = int(rule.get("from_port", raw_port))
        to_port = int(rule.get("to_port", raw_port))
    except (TypeError, ValueError):
        return set()
    if from_port == 0 and to_port == 0:
        return set(ADMIN_PORTS | DATABASE_PORTS)
    return set(range(min(from_port, to_port), max(from_port, to_port) + 1))


def _is_public_cidr(rule: dict[str, Any]) -> bool:
    text = " ".join(str(rule.get(key, "")) for key in ("cidr", "cidr_block", "cidr_blocks", "source"))
    return "0.0.0.0/0" in text or "::/0" in text


def _all_text(files: dict[str, str] | list[str]) -> str:
    return "\n".join(files.values()) if isinstance(files, dict) else "\n".join(files)


def _check_network(data: SecurityCheckInput, out: _FindingBuilder) -> None:
    terraform_text = _all_text(data.terraform_files)
    risky_public_rules = [rule for rule in data.security_group_rules if _is_public_cidr(rule)]
    public_db = [rule for rule in risky_public_rules if _port_range(rule) & DATABASE_PORTS]
    public_admin = [rule for rule in risky_public_rules if _port_range(rule) & ADMIN_PORTS]

    if public_db:
        out.add(
            title="Public database or cache port is exposed",
            severity=SecuritySeverity.CRITICAL,
            affected_component="network.security_groups",
            evidence=json.dumps(public_db[:3], sort_keys=True),
            impact="Internet exposure of Postgres, Redis, or another data service can lead to credential attacks and data loss.",
            fix_steps=["Remove 0.0.0.0/0 from database/cache ingress.", "Allow only the app security group or private subnet CIDRs."],
            category="network",
        )
    elif "security_groups = [aws_security_group.app.id]" in terraform_text and "from_port       = 5432" in terraform_text:
        out.pass_check("Database security group is restricted to app tier")

    if public_admin:
        out.add(
            title="Open admin port from the internet",
            severity=SecuritySeverity.CRITICAL,
            affected_component="network.security_groups",
            evidence=json.dumps(public_admin[:3], sort_keys=True),
            impact="Public SSH/RDP/admin ingress creates a direct management-plane attack path.",
            fix_steps=["Close public admin ports.", "Use SSM Session Manager, VPN, or a hardened bastion with limited CIDRs."],
            category="network",
        )
    else:
        out.pass_check("No public admin ports detected in supplied security group rules")

    if any(_is_public_cidr(rule) and _port_range(rule) & {0, 1, 2, 3, 4, 5} for rule in data.nacl_rules):
        out.add(
            title="Risky broad NACL rule",
            severity=SecuritySeverity.WARNING,
            affected_component="network.nacl",
            evidence="NACL input contains public all-port ingress.",
            impact="A permissive NACL weakens subnet isolation if security groups are misconfigured later.",
            fix_steps=["Use least-privilege NACL rules.", "Keep admin and database ports private."],
            category="network",
        )
    else:
        out.pass_check("No risky NACL rules supplied")

    if data.controls.get("waf_enabled") or "aws_wafv2" in terraform_text:
        out.pass_check("WAF posture is present")
    else:
        out.add(
            title="WAF is not configured",
            severity=SecuritySeverity.WARNING,
            affected_component="network.waf",
            evidence="No WAF control or aws_wafv2 resource detected.",
            impact="The public edge lacks managed request filtering for common attacks.",
            fix_steps=["Attach AWS WAF to the public ALB.", "Enable managed common, SQLi, and known-bad-input rule groups."],
            category="network",
        )

    if data.controls.get("https_enforced") or 'aws_lb_listener" "https' in terraform_text or "listen 443 ssl" in terraform_text:
        out.pass_check("HTTPS/TLS enforcement is configured")
    else:
        out.add(
            title="HTTPS/TLS enforcement is missing",
            severity=SecuritySeverity.HIGH,
            affected_component="network.tls",
            evidence="No HTTPS listener or TLS control detected.",
            impact="Credentials and trading dashboard data can cross the network over cleartext HTTP.",
            fix_steps=["Terminate TLS at ALB or nginx.", "Redirect HTTP to HTTPS and enable HSTS."],
            category="network",
        )


def _check_api(data: SecurityCheckInput, out: _FindingBuilder) -> None:
    root = Path(data.repo_root or _default_repo_root())
    main_py = _read_text(root / "services" / "trading-service" / "Backend" / "presentation" / "api" / "main.py")
    auth_py = _read_text(root / "services" / "trading-service" / "Backend" / "presentation" / "api" / "auth.py")

    if data.controls.get("api_rate_limiting") or "rate_limiter.check" in auth_py:
        out.pass_check("API login rate limiting is present")
    else:
        out.add(
            title="API rate limiting is missing",
            severity=SecuritySeverity.WARNING,
            affected_component="api.auth",
            evidence="No rate limiter evidence detected.",
            impact="Login and write endpoints are more exposed to brute force or burst abuse.",
            fix_steps=["Enable Redis-backed rate limiting.", "Add edge/WAF rate rules for auth and trading endpoints."],
            category="api",
        )

    if data.controls.get("jwt_validation") or ("verify_token" in auth_py and "compare_digest" in auth_py and "exp" in auth_py):
        out.pass_check("JWT/session token validation checks signature and expiry")
    else:
        out.add(
            title="JWT validation is incomplete",
            severity=SecuritySeverity.CRITICAL,
            affected_component="api.auth",
            evidence="Token signature or expiry validation was not detected.",
            impact="Attackers may reuse or forge dashboard/API credentials.",
            fix_steps=["Validate token signatures with constant-time comparison.", "Reject expired tokens and invalid roles."],
            category="api",
        )

    cors_text = main_py + "\n" + "\n".join(data.environment.values())
    if data.controls.get("cors_locked_down") or ("allow_origins=_allowed_origins()" in main_py and 'allow_origins=["*"]' not in cors_text):
        out.pass_check("CORS is explicit and not wildcarded")
    else:
        out.add(
            title="CORS allows broad origins",
            severity=SecuritySeverity.HIGH,
            affected_component="api.cors",
            evidence="Wildcard CORS or missing explicit-origin control detected.",
            impact="A hostile website may interact with the API from a victim browser.",
            fix_steps=["Set CORS_ALLOWED_ORIGINS to the exact production origin.", "Avoid wildcard origins with credentials."],
            category="api",
        )

    dashboard_api = _read_text(root / "services" / "trading-service" / "Backend" / "presentation" / "api" / "dashboard_api.py")
    if data.controls.get("api_auth_required", True) and "Depends(require_roles" in dashboard_api:
        out.pass_check("Dashboard API routes require role-based access")
    elif not data.controls.get("api_auth_required", True):
        out.add(
            title="Missing API authentication",
            severity=SecuritySeverity.CRITICAL,
            affected_component="api.routes",
            evidence="api_auth_required=false",
            impact="Security and trading dashboard data may be readable without a token.",
            fix_steps=["Require current_user or require_roles on all non-public endpoints.", "Keep /health as the only public status route."],
            category="api",
        )


def _check_kubernetes(data: SecurityCheckInput, out: _FindingBuilder) -> None:
    manifest = _all_text(data.kubernetes_manifests)
    if not manifest:
        out.add(
            title="Kubernetes manifests are not available",
            severity=SecuritySeverity.WARNING,
            affected_component="kubernetes.manifests",
            evidence="No Kubernetes YAML supplied or found.",
            impact="Cluster posture cannot be evaluated from source control.",
            fix_steps=["Commit deployment manifests or Helm values.", "Scan rendered manifests in CI."],
            category="kubernetes",
        )
        return

    if "kind: NetworkPolicy" in manifest or data.controls.get("kubernetes_network_policy"):
        out.pass_check("Kubernetes NetworkPolicy is present")
    else:
        out.add(title="Kubernetes NetworkPolicy is missing", severity=SecuritySeverity.WARNING, affected_component="kubernetes.network", evidence="No kind: NetworkPolicy found.", impact="Pods can often talk broadly inside the cluster if the CNI enforces no network policy.", fix_steps=["Add default-deny ingress/egress NetworkPolicies.", "Allow only required API, Redis, database, and observability paths."], category="kubernetes")

    if "kind: Role" in manifest or "kind: ClusterRole" in manifest or data.controls.get("kubernetes_rbac"):
        out.pass_check("Kubernetes RBAC manifests are present")
    else:
        out.add(title="Kubernetes RBAC is not declared", severity=SecuritySeverity.WARNING, affected_component="kubernetes.rbac", evidence="No Role, RoleBinding, ClusterRole, or ClusterRoleBinding found.", impact="Workloads may inherit broad default service account permissions.", fix_steps=["Create a dedicated service account.", "Bind only permissions required by the backend."], category="kubernetes")

    if "runAsNonRoot: true" in manifest:
        out.pass_check("Pods are configured to run as non-root")
    else:
        out.add(title="Pods are not forced to run as non-root", severity=SecuritySeverity.WARNING, affected_component="kubernetes.pod_security", evidence="runAsNonRoot: true not detected.", impact="A container escape or vulnerable process may gain root inside the container namespace.", fix_steps=["Set securityContext.runAsNonRoot=true.", "Specify a non-zero runAsUser."], category="kubernetes")

    if "readOnlyRootFilesystem: true" in manifest:
        out.pass_check("Pods use read-only root filesystem")
    else:
        out.add(title="Read-only root filesystem is missing", severity=SecuritySeverity.WARNING, affected_component="kubernetes.pod_security", evidence="readOnlyRootFilesystem: true not detected.", impact="Runtime compromise can more easily persist files inside the container.", fix_steps=["Set readOnlyRootFilesystem=true.", "Mount explicit writable volumes for temp/cache directories."], category="kubernetes")

    if "resources:" in manifest and "limits:" in manifest and "requests:" in manifest:
        out.pass_check("Pod resource requests and limits are configured")
    else:
        out.add(title="Pod resource limits are missing", severity=SecuritySeverity.WARNING, affected_component="kubernetes.resources", evidence="resources.requests and resources.limits were not both detected.", impact="A noisy or compromised pod can starve the node and reduce dashboard availability.", fix_steps=["Set CPU and memory requests/limits for every container.", "Alert when pods throttle or OOMKill."], category="kubernetes")


def _check_containers(data: SecurityCheckInput, out: _FindingBuilder) -> None:
    docker_text = _all_text(data.dockerfiles)
    critical_vulns = [item for item in data.image_vulnerabilities if str(item.get("severity", "")).upper() in {"CRITICAL", "HIGH"}]
    if critical_vulns:
        out.add(title="Vulnerable container image detected", severity=SecuritySeverity.CRITICAL, affected_component="containers.images", evidence=json.dumps(critical_vulns[:3], sort_keys=True), impact="Known exploitable packages in runtime images can become a direct production compromise path.", fix_steps=["Rebuild on patched base images.", "Fail CI on critical/high image CVEs until remediated or risk-accepted."], category="containers")
    else:
        out.pass_check("No critical/high container image vulnerabilities supplied")

    if re.search(r"(?m)^USER\s+\S+", docker_text):
        out.pass_check("Dockerfiles declare non-default container users")
    else:
        out.add(title="Dockerfiles do not declare a non-root USER", severity=SecuritySeverity.WARNING, affected_component="containers.runtime", evidence="No USER instruction detected in Dockerfiles.", impact="Containers may run as root unless overridden by Kubernetes securityContext.", fix_steps=["Create a dedicated unprivileged user in each image.", "Run nginx/backend with non-root UID where possible."], category="containers")

    workflow_text = _all_text(data.workflow_files).lower()
    if any(token in workflow_text for token in ("trivy", "grype", "docker scout")):
        out.pass_check("Docker image vulnerability scan is present in CI")
    else:
        out.add(title="Docker image vulnerability scan is missing", severity=SecuritySeverity.WARNING, affected_component="containers.ci", evidence="No Trivy/Grype/Docker Scout step detected.", impact="Known vulnerable base images can reach production without a gate.", fix_steps=["Add Trivy or Grype scans to GitHub Actions.", "Upload SARIF results and fail on critical vulnerabilities."], category="containers")


def _check_iam_and_database(data: SecurityCheckInput, out: _FindingBuilder) -> None:
    terraform_text = _all_text(data.terraform_files)
    if re.search(r'"Action"\s*:\s*"\*"', terraform_text) and re.search(r'"Resource"\s*:\s*"\*"', terraform_text):
        out.add(title="IAM wildcard policy detected", severity=SecuritySeverity.HIGH, affected_component="iam.policies", evidence="Policy contains Action=* and Resource=*.", impact="A compromised workload role can access far more AWS resources than required.", fix_steps=["Scope actions and resources to exact services.", "Split read-only telemetry from deployment/admin permissions."], category="iam")
    else:
        out.pass_check("No obvious IAM Action=* Resource=* policy found")

    if data.controls.get("terraform_state_encrypted") or ("encrypt" in terraform_text and 'backend "s3"' in terraform_text):
        out.pass_check("Terraform state encryption control is present")
    else:
        out.add(title="Terraform state encryption is not declared", severity=SecuritySeverity.WARNING, affected_component="iam.terraform_state", evidence="No encrypted remote state backend detected.", impact="State files can contain database passwords, ARNs, and sensitive infrastructure metadata.", fix_steps=["Use an S3 backend with encrypt=true and DynamoDB locking.", "Restrict state bucket IAM to CI/CD operators only."], category="iam")

    if data.controls.get("database_encryption") or re.search(r"storage_encrypted\s*=\s*true", terraform_text):
        out.pass_check("Database encryption at rest is configured")
    else:
        out.add(title="Database encryption is not proven", severity=SecuritySeverity.WARNING, affected_component="database.storage", evidence="storage_encrypted=true or equivalent control not detected.", impact="A storage snapshot or disk compromise can expose trading and audit data.", fix_steps=["Enable storage encryption on RDS/Postgres volumes.", "Use KMS keys with restricted administrators."], category="database")

    if data.controls.get("database_backups") or re.search(r"backup_retention_period\s*=\s*[1-9]", terraform_text):
        out.pass_check("Database backup retention is configured")
    else:
        out.add(title="Database backup status is not proven", severity=SecuritySeverity.WARNING, affected_component="database.backups", evidence="backup_retention_period or backup control not detected.", impact="Operational mistakes or ransomware can become unrecoverable incidents.", fix_steps=["Enable automated backups with retention.", "Test restore procedures on a schedule."], category="database")

    root = Path(data.repo_root or _default_repo_root())
    audit_text = _read_text(root / "services" / "trading-service" / "Backend" / "domain" / "security" / "audit.py")
    if data.controls.get("audit_logs") or "write_audit_log" in audit_text:
        out.pass_check("Application audit logging is present")
    else:
        out.add(title="Audit logging is missing", severity=SecuritySeverity.WARNING, affected_component="database.audit", evidence="No write_audit_log evidence detected.", impact="Security incidents and trade-control changes are hard to investigate.", fix_steps=["Record auth, admin, trading, kill-switch, and broker events.", "Retain logs in append-only storage."], category="database")


def _check_devsecops(data: SecurityCheckInput, out: _FindingBuilder) -> None:
    workflow_text = _all_text(data.workflow_files).lower()
    expected = {
        "secret scanning": ["gitleaks", "check_no_secrets", "secret"],
        "dependency scanning": ["pip-audit", "npm audit", "dependency"],
        "terraform fmt": ["terraform fmt"],
        "terraform validate": ["terraform validate"],
        "terraform security scan": ["tfsec", "checkov", "trivy config"],
        "kubernetes manifest scan": ["kube-score", "kube-linter", "kubescape", "trivy config"],
        "unit tests": ["pytest"],
        "prometheus/grafana alerts": ["prometheus", "grafana", "alert"],
    }
    for title, needles in expected.items():
        control_key = title.replace(" ", "_").replace("/", "_")
        if any(needle in workflow_text for needle in needles) or data.controls.get(control_key):
            out.pass_check(f"DevSecOps pipeline includes {title}")
        else:
            out.add(title=f"DevSecOps pipeline missing {title}", severity=SecuritySeverity.WARNING, affected_component="devsecops.pipeline", evidence=f"No {title} step detected in workflow files.", impact="Security regressions can merge without automated feedback.", fix_steps=["Add the missing check to .github/workflows/security.yml.", "Make critical findings block merges."], category="devsecops")


def _status_for(findings: list[SecurityFinding]) -> SecurityStatus:
    if any(item.severity == SecuritySeverity.CRITICAL for item in findings):
        return SecurityStatus.CRITICAL
    if any(item.severity in {SecuritySeverity.HIGH, SecuritySeverity.WARNING} for item in findings):
        return SecurityStatus.WARNING
    return SecurityStatus.SECURE


def _score(findings: list[SecurityFinding], passed_count: int) -> int:
    score = 100
    for item in findings:
        score -= 25 if item.severity == SecuritySeverity.CRITICAL else 12 if item.severity == SecuritySeverity.HIGH else 5 if item.severity == SecuritySeverity.WARNING else 0
    if passed_count >= 10:
        score += 3
    return max(0, min(100, score))


def _cards(findings: list[SecurityFinding], passed: list[str]) -> list[SecurityDashboardCard]:
    cards: list[SecurityDashboardCard] = []
    for category in CATEGORY_ORDER:
        category_findings = [item for item in findings if item.category == category]
        status = _status_for(category_findings)
        score = _score(category_findings, len(passed))
        summary = "All high-risk checks passed." if not category_findings else category_findings[0].title
        cards.append(SecurityDashboardCard(name=category.replace("_", " ").title(), category=category, status=status, score=score, summary=summary, finding_count=len(category_findings)))
    return cards


def _recommendations(findings: list[SecurityFinding]) -> list[SecurityRecommendation]:
    order = {SecuritySeverity.CRITICAL: 0, SecuritySeverity.HIGH: 1, SecuritySeverity.WARNING: 2, SecuritySeverity.INFO: 3}
    ranked = sorted(findings, key=lambda item: order[item.severity])
    return [SecurityRecommendation(title=item.title, priority=item.severity, action=item.fix_steps[0] if item.fix_steps else "Review and document remediation.", affected_component=item.affected_component) for item in ranked[:10]]


def run_security_scan(payload: SecurityCheckInput | None = None, *, persist: bool = False) -> SecurityScanResult:
    data = _load_default_input(payload)
    out = _FindingBuilder()
    _check_network(data, out)
    _check_api(data, out)
    _check_kubernetes(data, out)
    _check_containers(data, out)
    _check_iam_and_database(data, out)
    _check_devsecops(data, out)

    criticals = [item for item in out.findings if item.severity == SecuritySeverity.CRITICAL]
    warnings = [item for item in out.findings if item.severity != SecuritySeverity.CRITICAL]
    status = _status_for(out.findings)
    score = _score(out.findings, len(out.passed))
    result = SecurityScanResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        overall_status=status,
        security_score=score,
        critical_findings=criticals,
        warnings=warnings,
        passed_checks=sorted(set(out.passed)),
        recommended_actions=_recommendations(out.findings),
        dashboard_summary=f"Security posture is {status.value} with {len(criticals)} critical finding(s), {len(warnings)} warning/high-risk finding(s), and score {score}/100.",
        dashboard_cards=_cards(out.findings, out.passed),
    )
    if persist:
        store_security_scan(result, scan_type=data.scan_type)
        result.trend = list_security_scan_history(limit=20)
    return result


def _connect_history() -> sqlite3.Connection:
    path = _history_db_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS security_scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            overall_status TEXT NOT NULL,
            security_score INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    return connection


def store_security_scan(result: SecurityScanResult, *, scan_type: str = "full") -> None:
    with _connect_history() as connection:
        connection.execute(
            "INSERT INTO security_scan_history (scan_type, timestamp, overall_status, security_score, payload_json) VALUES (?, ?, ?, ?, ?)",
            (scan_type, result.timestamp, result.overall_status.value, result.security_score, json.dumps(_dump_model(result), sort_keys=True)),
        )


def list_security_scan_history(limit: int = 20) -> list[dict[str, Any]]:
    with _connect_history() as connection:
        rows = connection.execute(
            "SELECT scan_type, timestamp, overall_status, security_score FROM security_scan_history ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [{"scan_type": row[0], "timestamp": row[1], "overall_status": row[2], "security_score": row[3]} for row in reversed(rows)]


def latest_security_dashboard(*, category: str | None = None) -> dict[str, Any]:
    result = run_security_scan(persist=True)
    body = _dump_model(result)
    if category:
        findings = body["critical_findings"] + body["warnings"]
        body["findings"] = [item for item in findings if item.get("category") == category]
        body["dashboard_cards"] = [item for item in body["dashboard_cards"] if item.get("category") == category]
    return body
