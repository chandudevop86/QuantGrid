from pathlib import Path
import re

import ast


def detect_exec_usage(file_path):

    findings = []

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:
            source = f.read()

        tree = ast.parse(source)

    except Exception:
        return findings


    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "exec"
            ):

                findings.append(
                    {
                        "id": "SECURITY-004",
                        "severity": "HIGH",
                        "issue": "Use of exec()",
                        "file": file_path,
                        "line": node.lineno,
                        "confidence": 0.95,
                        "evidence": "exec() function call detected"
                    }
                )

    return findings



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
IGNORE_DIRS = {
    "venv",
    ".venv",
    "__pycache__",
    ".git",
    "node_modules",
    "dist",
    "build"
}
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

