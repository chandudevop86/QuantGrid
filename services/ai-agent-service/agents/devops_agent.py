from scanner.repo_scanner import scan_repository
from scanner.rules.devops_rules import check_devops


def analyze_devops(path: str):

    findings = []

    files = scan_repository(path)

    for file in files:

        findings.extend(
            check_devops(file)
        )

    return {
        "agent": "DevOps Agent",
        "score": calculate_devops_score(findings),
        "findings": findings,
    }


def calculate_devops_score(findings):

    score = 100

    for finding in findings:

        severity = finding.get("severity")

        if severity == "HIGH":
            score -= 10

        elif severity == "MEDIUM":
            score -= 5

        elif severity == "LOW":
            score -= 2

    return max(score, 0)