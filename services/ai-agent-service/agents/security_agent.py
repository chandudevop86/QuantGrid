from collections import Counter

from scanner.repo_scanner import scan_repository
from scanner.rules.security_rules import check_security


SEVERITY_PENALTY = {
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2,
}


def analyze_security(path: str):
    """
    Scan all Python files for security issues and
    generate an overall security assessment.
    """

    findings = []

    files = scan_repository(path)

    for file in files:
        if file.endswith(".py"):
            findings.extend(check_security(file))

    # Remove duplicate findings
    findings = remove_duplicate_findings(findings)

    score = calculate_security_score(findings)

    severity_summary = Counter(
        finding["severity"]
        for finding in findings
    )

    return {
        "agent": "Security Agent",
        "score": score,
        "rating": security_rating(score),
        "summary": {
            "high": severity_summary["HIGH"],
            "medium": severity_summary["MEDIUM"],
            "low": severity_summary["LOW"],
            "total": len(findings),
        },
        "findings": findings,
    }


def remove_duplicate_findings(findings):
    """
    Remove duplicate findings based on
    (Rule ID, File, Issue)
    """

    unique = {}

    for finding in findings:
        key = (
            finding["id"],
            finding["file"],
            finding["issue"],
        )

        unique[key] = finding

    return list(unique.values())


def calculate_security_score(findings):
    """
    Calculate security score out of 100.
    """

    score = 100

    for finding in findings:

        severity = finding.get(
            "severity",
            ""
        ).upper()

        score -= SEVERITY_PENALTY.get(
            severity,
            1
        )

    return max(score, 0)


def security_rating(score):
    """
    Convert numeric score into rating.
    """

    if score >= 90:
        return "Excellent"

    if score >= 75:
        return "Good"

    if score >= 60:
        return "Needs Improvement"

    if score >= 40:
        return "Poor"

    return "Critical"


def print_security_summary(result):
    """
    Optional helper for CLI debugging.
    """

    print("\n========== Security Summary ==========")
    print(f"Agent   : {result['agent']}")
    print(f"Score   : {result['score']}/100")
    print(f"Rating  : {result['rating']}")
    print()

    summary = result["summary"]

    print(f"High    : {summary['high']}")
    print(f"Medium  : {summary['medium']}")
    print(f"Low     : {summary['low']}")
    print(f"Total   : {summary['total']}")
    print("======================================")