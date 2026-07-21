from datetime import datetime
from pathlib import Path


def generate_report(report):

    output = Path("reports/QuantGrid_AI_Audit_Report.md")

    findings = report.get("findings", [])


    high = [
        f for f in findings
        if f["severity"] == "HIGH"
    ]

    medium = [
        f for f in findings
        if f["severity"] == "MEDIUM"
    ]


    content = f"""
# QuantGrid AI Audit Report

Generated:
{datetime.now()}


## Executive Summary

Files Scanned:
{report.get("files_scanned")}


Total Findings:
{len(findings)}


High Risk:
{len(high)}


Medium Risk:
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


File:

{item['file']}


Recommendation:

Review trading safety controls.

---

"""


    content += """

# Medium Risk Findings

"""


    for item in medium:

        content += f"""
## {item['id']}

File:
{item['file']}

Issue:
{item['issue']}

Recommendation:
Improve exception handling.

---

"""


    output.parent.mkdir(
        exist_ok=True
    )

    output.write_text(
        content
    )


    return str(output)