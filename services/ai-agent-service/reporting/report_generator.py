from datetime import datetime
from pathlib import Path
from collections import defaultdict

SEVERITY_SCORE = {
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2,
}

def calculate_risk_score(findings):
    score = sum(
        SEVERITY_SCORE.get(
            finding.get("severity", "LOW"),
            1,
        )
        for finding in findings
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
        item["severity"] = finding.get("severity", "LOW")
        item["issue"] = finding.get("issue", "")
        item["count"] += 1

        file = finding.get("file")
        if file and file not in item["files"]:
            item["files"].append(file)

    return list(grouped.values())


def recommendation(rule_id):
    recommendations = {
        "TRADE-001": """
- Add pre-trade validation
- Enforce stop-loss
- Add position sizing
- Add broker circuit breaker
""",
        "CODE-001": """
- Replace bare except blocks
- Catch specific exceptions
- Add structured logging
- Preserve stack traces
""",
        "SECURITY-001": """
- Remove hardcoded secrets
- Store secrets in .env
- Use AWS Secrets Manager / Hashicorp Vault
""",
        "SECURITY-002": """
- Rotate AWS credentials immediately
- Remove exposed access keys
""",
        "SECURITY-003": """
- Remove eval()
- Use safe parsing
""",
        "SECURITY-004": """
- Remove exec()
- Replace with secure alternatives
""",
        "DOC-001": """
- Add module-level docstrings
- Document purpose and usage
""",
        "DOC-002": """
- Resolve TODO items
- Remove obsolete TODO comments
""",
        "DOC-003": """
- Address FIXME issues before release
- Track them as technical debt if needed
""",
        "DOC-004": """
- Improve inline code comments
- Document complex business logic
""",

    }
    return recommendations.get(
        rule_id,
        "- Review and fix identified issue.",
    )


def generate_report(report):
    documentation = report.get("documentation", {})
    documentation_score = documentation.get("score", 0)

    findings = report.get("findings", [])
    grouped = aggregate_findings(findings)
    score = calculate_risk_score(findings)
    rating = risk_rating(score)

    architecture = report.get("architecture", {})
    security = report.get("security", {})
    performance = report.get("performance", {})
    database = report.get("database", {})
    devops = report.get("devops", {})
    api = report.get("api", {})
    infrastructure = report.get("infrastructure", {})
    testing = report.get("testing", {})
    
    architecture_score = architecture.get("score", 0)
    security_score = security.get("score", 0)
    performance_score = performance.get("score", 0)
    database_score = database.get("score", 0)
    devops_score = devops.get("score", 0)
    api_score = api.get("score", 0)
    infrastructure_score = infrastructure.get("score", 0)
    testing_score = testing.get("score", 0)
    
    overall_health = int(
        (
            architecture_score
            + security_score
            + performance_score
            + database_score
            + devops_score
            + api_score
            +infrastructure_score 
            + testing_score
            + documentation_score
            + (100 - score)
        ) / 10
    )

    severity_groups = defaultdict(list)
    for item in grouped:
        severity = item.get("severity", "LOW").upper()
        severity_groups[severity].append(item)

    content = f"""# QuantGrid AI Audit Report

Generated:
{datetime.now():%Y-%m-%d %H:%M:%S}

---

# Executive Summary

Files Scanned:
{report.get("files_scanned", 0)}

Total Findings:
{len(findings)}

Unique Issues:
{len(grouped)}

Architecture Score:
{architecture_score}/100

Security Score:
{security_score}/100

Performance Score:
{performance_score}/100

API Score:
{api_score}/100

Documentation Score:
{documentation_score}/100

Risk Score:
{score}/100

Risk Rating:
**{rating}**

Overall Health:
{overall_health}/100

---

# Risk Distribution

| Severity | Count |
|----------|------:|
| HIGH | {len(severity_groups["HIGH"])} |
| MEDIUM | {len(severity_groups["MEDIUM"])} |
| LOW | {len(severity_groups["LOW"])} |

---
"""

    for severity in ["HIGH", "MEDIUM", "LOW"]:
        content += f"\n# {severity.title()} Findings\n"

        if not severity_groups[severity]:
            content += "\nNo findings.\n"
            continue

        for item in severity_groups[severity]:
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

    content += f"""
# Architecture Assessment

Architecture Score:
{architecture_score}/100

Agent:
{architecture.get("agent", "")}

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

    content += f"""
---

# Performance Assessment

Performance Score:
{performance_score}/100

Agent:
{performance.get("agent", "")}

Performance Findings:
{len(performance.get("findings", []))}
"""

    if performance.get("findings"):
        grouped_performance = aggregate_findings(performance["findings"])
        for item in grouped_performance:
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
            
    content += f"""
---

# DevOps Assessment

DevOps Score:
{devops_score}/100

Agent:
{devops.get("agent", "")}

DevOps Findings:
{len(devops.get("findings", []))}
"""

    content += f"""
---

# API Assessment

API Score:
{api_score}/100

Agent:
{api.get("agent", "")}

API Findings:
{len(api.get("findings", []))}
"""

    if api.get("findings"):
        grouped_api = aggregate_findings(api["findings"])
        for item in grouped_api:
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

        content += f"""

---

# Infrastructure Assessment

Infrastructure Score:
{infrastructure_score}/100

Agent:
{infrastructure.get("agent", "")}

Infrastructure Findings:
{len(infrastructure.get("findings", []))}

"""

if infrastructure.get("findings"):

    grouped_infra = aggregate_findings(
        infrastructure["findings"]
    )

    for item in grouped_infra:

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


    content += f"""
---


# Testing Assessment

Testing Score:
{testing_score}/100

Agent:
{testing.get("agent", "")}

Testing Findings:
{len(testing.get("findings", []))}
"""

    content += f"""
---

# Security Assessment

Security Score:
{security_score}/100

Agent:
{security.get("agent", "")}

Security Findings:
{len(security.get("findings", []))}
"""

    if security.get("findings"):
        grouped_security = aggregate_findings(security["findings"])
        for item in grouped_security:
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

    content += f"""

---

# Documentation Assessment

Documentation Score:
{documentation_score}/100

Agent:
{documentation.get("agent", "")}

Documentation Findings:
{len(documentation.get("findings", []))}

"""

    if documentation.get("findings"):

        grouped_doc = aggregate_findings(
            documentation["findings"]
        )

        for item in grouped_doc:

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

    output = Path(
        "reports/QuantGrid_AI_Audit_Report.md"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        content,
        encoding="utf-8",
    )

    return str(output)