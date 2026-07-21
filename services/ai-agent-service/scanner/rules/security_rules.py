from pathlib import Path
import re
import ast


# ---------------------------------------------------------
# False Positive Control
# ---------------------------------------------------------

TEST_PATHS = {
    "tests/",
    "/test_",
    "_test.py",
    "fixtures/",
    "fixture/",
    "mock/",
    "mocks/",
    "examples/",
}


PLACEHOLDER_VALUES = {
    "test",
    "testing",
    "dummy",
    "sample",
    "example",
    "changeme",
    "password",
    "secret",
    "token",
    "xxx",
    "123456",
    "abcd",
}


ENV_PATTERNS = [
    r"os\.getenv",
    r"os\.environ",
    r"environ\.get",
    r"settings\.",
    r"config\.",
]


# ---------------------------------------------------------
# Security Patterns
# ---------------------------------------------------------

PATTERNS = [

    (
        "SECURITY-001",
        "HIGH",
        r"(password|secret|token|api_key|apikey)\s*=\s*['\"]([^'\"]+)['\"]",
        "Possible hardcoded secret",
        "CWE-798",
        "A07:2021 Identification and Authentication Failures",
    ),


    (
        "SECURITY-002",
        "HIGH",
        r"AKIA[0-9A-Z]{16}",
        "AWS Access Key detected",
        "CWE-798",
        "A07:2021 Identification and Authentication Failures",
    ),


    (
        "SECURITY-005",
        "MEDIUM",
        r"pickle\.(loads|load)\s*\(",
        "Unsafe pickle deserialization",
        "CWE-502",
        "A08:2021 Software and Data Integrity Failures",
    ),


    (
        "SECURITY-006",
        "MEDIUM",
        r"subprocess\.(Popen|run|call).*shell\s*=\s*True",
        "Command execution with shell=True",
        "CWE-78",
        "A03:2021 Injection",
    ),


    (
        "SECURITY-007",
        "LOW",
        r"verify\s*=\s*False",
        "SSL verification disabled",
        "CWE-295",
        "A02:2021 Cryptographic Failures",
    ),


    (
        "SECURITY-008",
        "LOW",
        r"debug\s*=\s*True",
        "Debug mode enabled",
        "CWE-489",
        "A05:2021 Security Misconfiguration",
    ),

]



# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def is_test_file(file_path):

    path = str(file_path).lower()

    return any(
        item in path
        for item in TEST_PATHS
    )



def uses_environment(source):

    return any(
        re.search(
            pattern,
            source
        )
        for pattern in ENV_PATTERNS
    )



def secret_confidence(
    file_path,
    value
):

    value = value.lower().strip()


    # tests and fixtures
    if is_test_file(file_path):
        return 30


    # placeholders
    if value in PLACEHOLDER_VALUES:
        return 20


    # too short
    if len(value) < 8:
        return 40


    # real looking secret
    return 95



def line_number(
    source,
    position
):

    return (
        source[:position]
        .count("\n")
        + 1
    )



# ---------------------------------------------------------
# AST Checks
# ---------------------------------------------------------

def detect_exec_usage(file_path):

    findings = []


    try:

        source = Path(file_path).read_text(
            errors="ignore"
        )

        tree = ast.parse(source)


    except Exception:

        return findings



    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.Call
        ):

            if (
                isinstance(
                    node.func,
                    ast.Name
                )
                and node.func.id == "exec"
            ):

                findings.append(

                    {
                        "id": "SECURITY-004",
                        "category": "Code Execution",
                        "severity": "HIGH",
                        "title": "Use of exec()",
                        "issue":
                            "Dynamic execution using exec() detected",
                        "file":
                            str(file_path),
                        "line":
                            node.lineno,
                        "confidence":
                            95,
                        "evidence":
                            ast.get_source_segment(
                                source,
                                node
                            ),
                        "recommendation":
                            "Remove exec() and use explicit logic",
                        "cwe":
                            "CWE-94",
                        "owasp":
                            "A03:2021 Injection",
                        "status":
                            "OPEN"
                    }

                )


    return findings





def detect_eval_usage(file_path):

    findings = []


    try:

        source = Path(file_path).read_text(
            errors="ignore"
        )

        tree = ast.parse(source)


    except Exception:

        return findings



    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.Call
        ):

            if (

                isinstance(
                    node.func,
                    ast.Name
                )

                and node.func.id == "eval"

            ):

                findings.append(

                    {
                        "id":
                            "SECURITY-003",

                        "category":
                            "Code Execution",

                        "severity":
                            "HIGH",

                        "title":
                            "Use of eval()",

                        "issue":
                            "Dynamic evaluation detected",

                        "file":
                            str(file_path),

                        "line":
                            node.lineno,

                        "confidence":
                            95,

                        "evidence":
                            "eval() function call",

                        "recommendation":
                            "Replace eval with safe parsing",

                        "cwe":
                            "CWE-95",

                        "owasp":
                            "A03:2021 Injection",

                        "status":
                            "OPEN"
                    }

                )


    return findings



# ---------------------------------------------------------
# Main Scanner
# ---------------------------------------------------------

def check_security(file):

    findings = []


    try:

        source = Path(file).read_text(
            errors="ignore"
        )

    except Exception:

        return findings



    # AST checks

    findings.extend(
        detect_eval_usage(file)
    )


    findings.extend(
        detect_exec_usage(file)
    )



    # Regex checks

    for (
        rule_id,
        severity,
        pattern,
        issue,
        cwe,
        owasp

    ) in PATTERNS:



        for match in re.finditer(
            pattern,
            source,
            re.MULTILINE
        ):



            confidence = 80


            final_severity = severity



            if rule_id == "SECURITY-001":

                value = (
                    match.group(2)
                    if match.lastindex
                    else match.group(0)
                )


                confidence = secret_confidence(
                    file,
                    value
                )


                if confidence < 50:

                    final_severity = "LOW"



                # ignore environment configs

                if uses_environment(source):

                    confidence -= 20



            findings.append(

                {
                    "id":
                        rule_id,

                    "severity":
                        final_severity,

                    "issue":
                        issue,

                    "file":
                        str(file),

                    "line":
                        line_number(
                            source,
                            match.start()
                        ),

                    "confidence":
                        confidence,

                    "evidence":
                        match.group(0),

                    "cwe":
                        cwe,

                    "owasp":
                        owasp,

                    "status":
                        "OPEN"
                }

            )



    return findings