import re


SECRET_PATTERNS = [
    r"password\s*=\s*['\"].+['\"]",
    r"api_key\s*=\s*['\"].+['\"]",
    r"secret\s*=\s*['\"].+['\"]",
    r"token\s*=\s*['\"].+['\"]"
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
