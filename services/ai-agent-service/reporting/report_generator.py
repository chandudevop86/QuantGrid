from datetime import datetime
from pathlib import Path
from collections import defaultdict


SEVERITY_SCORE = {
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2
}


def calculate_risk_score(findings):

    score = 0


    for finding in findings:

        score += SEVERITY_SCORE.get(
            finding.get("severity"),
            1
        )


    return min(score,100)

def risk_rating(score):

    if score >= 60:
        return "CRITICAL"

    if score >= 30:
        return "HIGH"

    if score >= 15:
        return "MEDIUM"

    return "LOW"

def aggregate_findings(findings):

    grouped = defaultdict(
        lambda: {
            "id": "",
            "severity": "",
            "issue": "",
            "files": [],
            "count": 0
        }
    )


    for finding in findings:

        key = (
            finding["id"],
            finding["issue"]
            
        )


        item = grouped[key]

        item["id"] = finding["id"]
        item["severity"] = finding["severity"]
        item["issue"] = finding["issue"]
        item["count"] += 1
        if finding["file"] not in item["files"]:
            item["files"].append(
            finding["file"]
        )
        


    return list(grouped.values())


def recommendation(finding):

    if finding["id"] == "TRADE-001":

        return """
- Add pre-trade risk validation
- Enforce stop loss checks
- Add position size limits
- Add broker circuit breaker
"""


    if finding["id"] == "CODE-001":

        return """
- Replace bare except blocks
- Add structured logging
- Preserve production stack traces
"""


    return """
- Review and fix identified issue
"""


def generate_report(report):

    findings = report.get(
        "findings",
        []
    )


    grouped = aggregate_findings(
        findings
    )


    score = calculate_risk_score(
        findings
    )


    rating = risk_rating(
        score
    )


    high = [
        f for f in grouped
        if f["severity"] == "HIGH"
    ]


    medium = [
        f for f in grouped
        if f["severity"] == "MEDIUM"
    ]


    content = f"""
# QuantGrid AI Audit Report


Generated:

{datetime.now()}


# Executive Summary


Files Scanned:

{report.get("files_scanned")}


Total Findings:

{len(findings)}


Unique Issues:

{len(grouped)}


Risk Score:

{score}/100


Risk Rating:

{rating}



---

# Risk Distribution


High:

{len(high)}


Medium:

{len(medium)}



---

# High Risk Findings

"""


    for item in high:

        content += f"""

## {item['id']}


Severity:

{item['severity']}


Issue:

{item['issue']}


Affected Files:

{len(item['files'])}


"""

        for file in item["files"]:
            content += f"- {file}\n"


        content += """

Recommendation:

"""

        content += recommendation(item)

        content += "\n---\n"



    content += """

# Medium Risk Findings

"""


    for item in medium:

        content += f"""

## {item['id']}


Issue:

{item['issue']}


Occurrences:

{item['count']}


Files:


"""


        for file in item["files"]:
            content += f"- {file}\n"


        content += """

Recommendation:

"""


        content += recommendation(item)

        content += "\n---\n"



    output = Path(
        "reports/QuantGrid_AI_Audit_Report.md"
        
    )
    
    architecture = report.get(
    "architecture",
    {}
    )
    architecture = report.get("architecture", {})

    content += f"""

# Architecture Assessment

Score:

{architecture.get("score", "N/A")}/100

Agent:

{architecture.get("agent", "")}

Services:

"""

    for service in architecture.get("services", []):
        content += f"- {service}\n"

    content += "\nTechnologies:\n\n"

    for tech in architecture.get("technologies", []):
        content += f"- {tech}\n"

    content += "\nWarnings:\n\n"

    for warning in architecture.get("warnings", []):
        content += f"- {warning}\n"

    content += "\nRecommendations:\n\n"

    for rec in architecture.get("recommendations", []):
        content += f"- {rec}\n"

    output.parent.mkdir(
        exist_ok=True
    )


    output.write_text(
        content
    )


    return str(output)


content += f"""

# Architecture Assessment


Score:

{architecture.get("score","N/A")}/100


Agent:

{architecture.get("agent","")}


Services:


"""


for service in architecture.get("services",[]):

    content += f"- {service}\n"



content += """

Technologies:


"""


for tech in architecture.get("technologies",[]):

    content += f"- {tech}\n"



content += """

Warnings:


"""


for warning in architecture.get("warnings",[]):

    content += f"- {warning}\n"



content += """

Recommendations:


"""


for rec in architecture.get("recommendations",[]):

    content += f"- {rec}\n"