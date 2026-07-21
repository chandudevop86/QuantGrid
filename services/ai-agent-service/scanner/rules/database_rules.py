import re


def check_database(file_path: str, code: str):

    findings = []

    patterns = [
        (
            "DB-001",
            "HIGH",
            r"SELECT\s+\*",
            "SELECT * detected"
        ),
        (
            "DB-002",
            "HIGH",
            r"(execute|executemany)\s*\(\s*f?[\"'].*%s",
            "Possible SQL injection"
        ),
        (
            "DB-003",
            "MEDIUM",
            r"commit\s*\(",
            "Manual transaction commit"
        ),
        (
            "DB-004",
            "LOW",
            r"cursor\s*\(",
            "Raw database cursor usage"
        ),
        (
            "DB-005",
            "MEDIUM",
            r"sqlite3\.connect",
            "SQLite database detected"
        ),
        (
            "DB-006",
            "LOW",
            r"fetchall\s*\(",
            "fetchall() may load excessive data"
        ),
        (
            "DB-007",
            "MEDIUM",
            r"DELETE\s+FROM",
            "DELETE statement detected"
        ),
        (
            "DB-008",
            "MEDIUM",
            r"UPDATE\s+.*SET",
            "UPDATE statement detected"
        ),
    ]

    for rule_id, severity, pattern, issue in patterns:

        if re.search(pattern, code, re.IGNORECASE):

            findings.append({
                "id": rule_id,
                "severity": severity,
                "issue": issue,
                "file": file_path,
            })

    return findings