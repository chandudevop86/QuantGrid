import re


def check_performance(file_path: str, code: str):

    findings = []

    # PERF-001
    if re.search(r"for .*:\s*\n\s*for ", code):

        findings.append({
            "id": "PERF-001",
            "severity": "MEDIUM",
            "issue": "Nested loops detected",
            "file": file_path,
        })

    # PERF-002
    if ".read()" in code and "chunk" not in code:

        findings.append({
            "id": "PERF-002",
            "severity": "LOW",
            "issue": "Large file read into memory",
            "file": file_path,
        })

    # PERF-003
    if "requests.get(" in code and "timeout=" not in code:

        findings.append({
            "id": "PERF-003",
            "severity": "MEDIUM",
            "issue": "HTTP request without timeout",
            "file": file_path,
        })

    # PERF-004
    if "time.sleep(" in code:

        findings.append({
            "id": "PERF-004",
            "severity": "LOW",
            "issue": "Blocking sleep detected",
            "file": file_path,
        })

    # PERF-005
    if ".append(" in code and "for" in code and "list(" not in code:

        findings.append({
            "id": "PERF-005",
            "severity": "LOW",
            "issue": "Loop append may benefit from comprehension",
            "file": file_path,
        })

    # PERF-006
    if "SELECT *" in code.upper():

        findings.append({
            "id": "PERF-006",
            "severity": "MEDIUM",
            "issue": "Database query uses SELECT *",
            "file": file_path,
        })

    # PERF-007
    if "print(" in code:

        findings.append({
            "id": "PERF-007",
            "severity": "LOW",
            "issue": "Debug print statements found",
            "file": file_path,
        })

    # PERF-008
    if "while True" in code:

        findings.append({
            "id": "PERF-008",
            "severity": "MEDIUM",
            "issue": "Potential infinite loop",
            "file": file_path,
        })

    return findings