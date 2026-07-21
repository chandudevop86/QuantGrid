from scanner.repo_scanner import scan_repository
from scanner.rules.testing_rules import check_testing


def analyze_testing(path: str):

    findings = []

    files = scan_repository(path)

    for file in files:

        if file.endswith(".py"):
            findings.extend(check_testing(file))

    return {
        "agent": "Testing Agent",
        "score": calculate_testing_score(findings),
        "findings": findings,
    }


def calculate_testing_score(findings):

    score = 100

    for finding in findings:

        sev = finding.get("severity")

        if sev == "HIGH":
            score -= 10

        elif sev == "MEDIUM":
            score -= 5

        elif sev == "LOW":
            score -= 2

    return max(score, 0)