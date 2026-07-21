from datetime import datetime
from pathlib import Path
from collections import defaultdict

# ============================================================
# Severity Weights
# ============================================================

SEVERITY_SCORE = {
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2,
}
import ast


def detect_eval_usage(file_path):

    findings = []

    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)

    except SyntaxError:
        return findings


    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "eval"
            ):

                findings.append(
                    {
                        "id": "SECURITY-003",
                        "severity": "HIGH",
                        "issue": "Use of eval()",
                        "file": file_path,
                        "line": node.lineno,
                        "confidence": 0.95,
                    }
                )

    return findings
# ============================================================
# Risk Calculation
# ============================================================

def calculate_risk_score(findings):
    score = 0

    for finding in findings:
        score += SEVERITY_SCORE.get(
            finding.get("severity", "LOW").upper(),
            1,
        )

    return min(score, 100)


def risk_rating(score):

    if score >= 60:
        return "CRITICAL"

    elif score >= 30:
        return "HIGH"

    elif score >= 15:
        return "MEDIUM"

    return "LOW"


# ============================================================
# Aggregate Duplicate Findings
# ============================================================

def aggregate_findings(findings):

    grouped = defaultdict(
        lambda: {
            "id": "",
            "severity": "",
            "issue": "",
            "files": [],
            "count": 0,
        }
    )

    for finding in findings:

        key = (
            finding.get("id"),
            finding.get("issue"),
        )

        item = grouped[key]

        item["id"] = finding.get("id", "")
        item["severity"] = finding.get(
            "severity",
            "LOW",
        )

        item["issue"] = finding.get(
            "issue",
            "",
        )

        item["count"] += 1

        file = finding.get("file")

        if file and file not in item["files"]:
            item["files"].append(file)

    return list(grouped.values())


# ============================================================
# Recommendations Database
# ============================================================

def recommendation(rule_id):

    recommendations = {

        # ----------------------------
        # Code
        # ----------------------------

        "CODE-001": """
- Replace bare except blocks
- Catch specific exceptions
- Preserve stack traces
- Add structured logging
""",

        "CODE-002": """
- Reduce function complexity
- Split large methods
- Improve readability
""",

        "CODE-003": """
- Remove duplicated logic
- Extract helper functions
""",

        # ----------------------------
        # Trading
        # ----------------------------

        "TRADE-001": """
- Add pre-trade validation
- Validate stop loss
- Validate quantity
- Validate capital allocation
- Add circuit breaker
""",

        "TRADE-002": """
- Prevent duplicate orders
- Add idempotency protection
""",

        # ----------------------------
        # Security
        # ----------------------------

        "SECURITY-001": """
- Remove hardcoded secrets
- Move credentials into .env
- Use AWS Secrets Manager
""",

        "SECURITY-002": """
- Rotate AWS credentials
- Delete exposed keys
""",

        "SECURITY-003": """
- Replace eval()
- Use safe parsing
""",

        "SECURITY-004": """
- Remove exec()
- Use safe alternatives
""",

        "SECURITY-005": """
- Avoid pickle.loads()
- Prefer JSON serialization
""",

        "SECURITY-006": """
- Validate subprocess input
- Avoid shell=True
""",

        "SECURITY-007": """
- Enable SSL verification
""",

        "SECURITY-008": """
- Disable debug mode
""",

        # ----------------------------
        # Performance
        # ----------------------------

        "PERF-001": """
- Cache repeated queries
- Use Redis
""",

        "PERF-002": """
- Avoid nested loops
- Improve algorithm complexity
""",

        "PERF-003": """
- Use async I/O
- Avoid blocking calls
""",

        "PERF-004": """
- Optimize database queries
""",

        # ----------------------------
        # Database
        # ----------------------------

        "DB-001": """
- Parameterize SQL queries
""",

        "DB-002": """
- Add indexes
""",

        "DB-003": """
- Use connection pooling
""",

        "DB-004": """
- Add transaction handling
""",

        # ----------------------------
        # DevOps
        # ----------------------------

        "DEVOPS-001": """
- Add CI/CD pipeline
""",

        "DEVOPS-002": """
- Improve Docker build
""",

        "DEVOPS-003": """
- Pin dependency versions
""",

        "DEVOPS-004": """
- Add deployment rollback
""",

        # ----------------------------
        # API
        # ----------------------------

        "API-001": """
- Implement REST best practices
- Version APIs
""",

        "API-002": """
- Protect endpoints
- Use JWT authentication
""",

        "API-003": """
- Validate request payloads
- Use Pydantic models
""",

        "API-004": """
- Improve exception handling
""",

        "API-005": """
- Add OpenAPI documentation
""",

        "API-006": """
- Restrict CORS
""",

        "API-007": """
- Enable rate limiting
""",

        "API-101": """
- Protect endpoint with Depends()
""",

        "API-102": """
- Validate requests
""",

        "API-103": """
- Handle HTTPException properly
""",

        "API-104": """
- Define response_model
""",

        # ----------------------------
        # Infrastructure
        # ----------------------------

        "INFRA-001": """
- Add Docker HEALTHCHECK
""",

        "INFRA-002": """
- Configure restart policy
""",

        "INFRA-003": """
- Enable S3 Versioning
""",

        "INFRA-004": """
- Enable encryption at rest
""",

        "INFRA-005": """
- Configure Kubernetes Liveness Probe
""",

        "INFRA-006": """
- Configure Readiness Probe
""",

        # ----------------------------
        # Testing
        # ----------------------------

        "TEST-001": """
- Increase unit test coverage
""",

        "TEST-002": """
- Add integration tests
""",

        "TEST-003": """
- Automate regression testing
""",

        # ----------------------------
        # Documentation
        # ----------------------------

        "DOC-001": """
- Add module docstrings
""",

        "DOC-002": """
- Resolve TODO comments
""",

        "DOC-003": """
- Resolve FIXME comments
""",

        "DOC-004": """
- Improve inline documentation
""",
    }

    return recommendations.get(
        rule_id,
        "- Review and fix this issue.",
    )
    # ============================================================
# Generic Findings Builder
# ============================================================

def _build_standard_findings_block(findings):

    if not findings:
        return ""

    content = ""

    grouped = aggregate_findings(findings)

    for item in grouped:

        content += f"""
## {item["id"]}

Severity:
{item["severity"]}

Issue:
{item["issue"]}

Occurrences:
{item["count"]}

Affected Files:
"""

        for file in item["files"]:
            content += f"- {file}\n"

        content += "\nRecommendation:\n"
        content += recommendation(item["id"])
        content += "\n\n---\n"

    return content


# ============================================================
# Architecture Section
# ============================================================

def build_architecture_section(architecture):

    score = architecture.get("score", 0)

    content = f"""

---

# Architecture Assessment

Architecture Score:
{score}/100

Agent:
{architecture.get("agent","")}

Services:
"""

    for service in architecture.get("services", []):
        content += f"- {service}\n"

    content += "\nTechnologies:\n"

    for tech in architecture.get("technologies", []):
        content += f"- {tech}\n"

    content += "\nWarnings:\n"

    for warning in architecture.get("warnings", []):
        content += f"- {warning}\n"

    content += "\nRecommendations:\n"

    for rec in architecture.get("recommendations", []):
        content += f"- {rec}\n"

    return content


# ============================================================
# Security Section
# ============================================================

def build_security_section(security):

    findings = security.get("findings", [])

    content = f"""

---

# Security Assessment

Security Score:
{security.get("score",0)}/100

Agent:
{security.get("agent","")}

Security Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# Performance Section
# ============================================================

def build_performance_section(performance):

    findings = performance.get("findings", [])

    content = f"""

---

# Performance Assessment

Performance Score:
{performance.get("score",0)}/100

Agent:
{performance.get("agent","")}

Performance Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# Database Section
# ============================================================

def build_database_section(database):

    findings = database.get("findings", [])

    content = f"""

---

# Database Assessment

Database Score:
{database.get("score",0)}/100

Agent:
{database.get("agent","")}

Database Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# DevOps Section
# ============================================================

def build_devops_section(devops):

    findings = devops.get("findings", [])

    content = f"""

---

# DevOps Assessment

DevOps Score:
{devops.get("score",0)}/100

Agent:
{devops.get("agent","")}

DevOps Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# API Section
# ============================================================

def build_api_section(api):

    findings = api.get("findings", [])

    content = f"""

---

# API Assessment

API Score:
{api.get("score",0)}/100

Agent:
{api.get("agent","")}

API Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# Infrastructure Section
# ============================================================

def build_infrastructure_section(infrastructure):

    findings = infrastructure.get("findings", [])

    content = f"""

---

# Infrastructure Assessment

Infrastructure Score:
{infrastructure.get("score",0)}/100

Agent:
{infrastructure.get("agent","")}

Infrastructure Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# Testing Section
# ============================================================

def build_testing_section(testing):

    findings = testing.get("findings", [])

    content = f"""

---

# Testing Assessment

Testing Score:
{testing.get("score",0)}/100

Agent:
{testing.get("agent","")}

Testing Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content


# ============================================================
# Documentation Section
# ============================================================

def build_documentation_section(documentation):

    findings = documentation.get("findings", [])

    content = f"""

---

# Documentation Assessment

Documentation Score:
{documentation.get("score",0)}/100

Agent:
{documentation.get("agent","")}

Documentation Findings:
{len(findings)}

"""

    content += _build_standard_findings_block(findings)

    return content
def generate_report(report):

    findings = report.get("findings", [])

    risk_score = calculate_risk_score(findings)

    content = "# QuantGrid AI Audit Report\n\n"

    content += f"""
Generated:
{datetime.now()}


# Executive Summary

Files Scanned:
{report.get("files_scanned",0)}

Total Findings:
{len(findings)}

Risk Score:
{risk_score}/100

Risk Rating:
{risk_rating(risk_score)}

"""


    # ----------------------------------------
    # Severity Summary
    # ----------------------------------------

    severity_count = defaultdict(int)

    for finding in findings:
        severity = finding.get(
            "severity",
            "LOW"
        ).upper()

        severity_count[severity] += 1


    content += """

---

# Severity Summary

"""


    for severity, count in severity_count.items():

        content += (
            f"- {severity}: {count}\n"
        )


    # ----------------------------------------
    # Agent Assessments
    # ----------------------------------------

    content += build_architecture_section(
        report.get("architecture", {})
    )


    content += build_security_section(
        report.get("security", {})
    )


    content += build_performance_section(
        report.get("performance", {})
    )


    content += build_database_section(
        report.get("database", {})
    )


    content += build_devops_section(
        report.get("devops", {})
    )


    content += build_api_section(
        report.get("api", {})
    )


    content += build_testing_section(
        report.get("testing", {})
    )


    content += build_documentation_section(
        report.get("documentation", {})
    )


    content += build_infrastructure_section(
        report.get("infrastructure", {})
    )


    # ----------------------------------------
    # Consolidated Findings
    # ----------------------------------------

    content += """

---

# Consolidated Findings

"""


    content += _build_standard_findings_block(
        findings
    )


    # ----------------------------------------
    # Save Report
    # ----------------------------------------

    output = Path(
        "reports/QuantGrid_AI_Audit_Report.md"
    )


    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    output.write_text(
        content,
        encoding="utf-8"
    )


    return str(output)