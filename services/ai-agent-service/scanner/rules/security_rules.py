from pathlib import Path
import re

def check_security(file):

    findings = []

    try:
        text = Path(file).read_text(errors="ignore")
    except Exception:
        return findings

    for rule_id, severity, pattern, issue in PATTERNS:

        if re.search(pattern, text):

            findings.append({
                "id": rule_id,
                "severity": severity,
                "issue": issue,
                "file": file,
            })

    return findings

SECRET_PATTERNS = [
    r"password\s*=\s*['\"].+['\"]",
    r"api_key\s*=\s*['\"].+['\"]",
    r"secret\s*=\s*['\"].+['\"]",
    r"token\s*=\s*['\"].+['\"]"
]
PATTERNS = [

    (
        "SECURITY-001",
        "HIGH",
        r"(password|secret|token)\s*=\s*['\"].+['\"]",
        "Possible hardcoded secret",
    ),

    (
        "SECURITY-002",
        "HIGH",
        r"AKIA[0-9A-Z]{16}",
        "AWS Access Key detected",
    ),

    (
        "SECURITY-003",
        "HIGH",
        r"eval\s*\(",
        "Use of eval()",
    ),

    (
        "SECURITY-004",
        "HIGH",
        r"exec\s*\(",
        "Use of exec()",
    ),

    (
        "SECURITY-005",
        "MEDIUM",
        r"pickle\.loads",
        "Unsafe pickle deserialization",
    ),

    (
        "SECURITY-006",
        "MEDIUM",
        r"subprocess\.Popen",
        "Subprocess execution",
    ),

    (
        "SECURITY-007",
        "LOW",
        r"verify=False",
        "SSL verification disabled",
    ),

    (
        "SECURITY-008",
        "LOW",
        r"debug\s*=\s*True",
        "Debug mode enabled",
    ),
]

def check_security(file_path, code):

    findings = []


    for pattern in SECRET_PATTERNS:

        matches = re.findall(
            pattern,
            code,
            re.IGNORECASE
        )


        if matches:

            findings.append(
                {
                    "id":"SECURITY-001",
                    "severity":"HIGH",
                    "issue":"Possible hardcoded secret",
                    "file":file_path
                }
            )


    return findings
