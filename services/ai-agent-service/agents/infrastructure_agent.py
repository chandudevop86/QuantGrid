from pathlib import Path

from scanner.repo_scanner import scan_repository
from scanner.rules.infrastructure_rules import check_infrastructure


def analyze_infrastructure(path):

    findings = []

    files = scan_repository(path)

    extensions = (
        ".py",
        ".tf",
        ".yaml",
        ".yml",
        ".json",
    )

    for file in files:

        if (
            file.endswith(extensions)
            or Path(file).name == "Dockerfile"
        ):

            try:

                code = Path(file).read_text(
                    errors="ignore"
                )

                findings.extend(
                    check_infrastructure(
                        file,
                        code
                    )
                )

            except Exception:
                pass

    return {
        "agent": "Infrastructure Agent",
        "score": calculate_score(findings),
        "findings": findings,
    }


def calculate_score(findings):

    score = 100

    for finding in findings:

        severity = finding["severity"]

        if severity == "HIGH":
            score -= 10

        elif severity == "MEDIUM":
            score -= 5

        elif severity == "LOW":
            score -= 2

    return max(score, 0)