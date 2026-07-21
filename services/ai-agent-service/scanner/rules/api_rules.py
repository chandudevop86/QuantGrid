from pathlib import Path
import re


RULES = [

    (
        "API-001",
        "HIGH",
        r"@app\.(get|post|put|delete|patch)\(",
        "API endpoint detected"
    ),

    (
        "API-002",
        "HIGH",
        r"Depends\s*\(",
        "Authentication dependency present"
    ),

    (
        "API-003",
        "HIGH",
        r"OAuth2|JWT|Bearer",
        "Authentication mechanism found"
    ),

    (
        "API-004",
        "MEDIUM",
        r"BaseModel",
        "Pydantic request validation detected"
    ),

    (
        "API-005",
        "MEDIUM",
        r"HTTPException",
        "HTTP error handling implemented"
    ),

    (
        "API-006",
        "LOW",
        r"response_model",
        "Response model defined"
    ),

    (
        "API-007",
        "LOW",
        r"status_code",
        "Status codes specified"
    ),

    (
        "API-008",
        "MEDIUM",
        r"tags=",
        "OpenAPI tags configured"
    ),

    (
        "API-009",
        "MEDIUM",
        r"summary=",
        "Endpoint summary provided"
    ),

    (
        "API-010",
        "HIGH",
        r"CORSMiddleware",
        "CORS middleware configured"
    ),

    (
        "API-011",
        "MEDIUM",
        r"Request",
        "Request object usage detected"
    ),

    (
        "API-012",
        "LOW",
        r"Response",
        "Response object usage detected"
    ),

    (
        "API-013",
        "HIGH",
        r"rate.?limit|Limiter|slowapi",
        "Rate limiting configured"
    ),

    (
        "API-014",
        "MEDIUM",
        r"middleware",
        "Middleware implemented"
    ),

    (
        "API-015",
        "LOW",
        r"openapi_url",
        "OpenAPI customization found"
    ),
]


def check_api(file_path):

    findings = []

    try:
        code = Path(file_path).read_text(errors="ignore")
    except Exception:
        return findings

    endpoint_found = False

    for rule_id, severity, pattern, issue in RULES:

        if re.search(pattern, code, re.IGNORECASE):

            endpoint_found = True

            findings.append({
                "id": rule_id,
                "severity": severity,
                "issue": issue,
                "file": file_path,
            })

    if endpoint_found:

        if "Depends(" not in code:
            findings.append({
                "id": "API-101",
                "severity": "HIGH",
                "issue": "Endpoint without dependency injection",
                "file": file_path,
            })

        if "BaseModel" not in code:
            findings.append({
                "id": "API-102",
                "severity": "MEDIUM",
                "issue": "Request validation missing",
                "file": file_path,
            })

        if "HTTPException" not in code:
            findings.append({
                "id": "API-103",
                "severity": "MEDIUM",
                "issue": "HTTP error handling missing",
                "file": file_path,
            })

        if "response_model" not in code:
            findings.append({
                "id": "API-104",
                "severity": "LOW",
                "issue": "Response model not defined",
                "file": file_path,
            })

    return findings