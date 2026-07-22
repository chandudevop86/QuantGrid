from pathlib import Path
import re
from models import (
    Finding,
    Severity,
    Category,
    Evidence,
)




RULES = [

    (
        "API-001",
        Severity.INFO,
        re.compile(r"@app\.(get|post|put|delete|patch)\(", re.IGNORECASE),
        "API Endpoint Detected",
        "FastAPI endpoint decorator detected."
    ),

    (
        "API-002",
        Severity.HIGH,
        re.compile(r"Depends\s*\(", re.IGNORECASE),
        "Authentication Dependency Present",
        "FastAPI dependency injection detected."
    ),

    (
        "API-003",
        Severity.HIGH,
        re.compile(r"OAuth2|JWT|Bearer", re.IGNORECASE),
        "Authentication Mechanism Found",
        "OAuth2, JWT or Bearer authentication detected."
    ),

    (
        "API-004",
        Severity.MEDIUM,
        re.compile(r"BaseModel", re.IGNORECASE),
        "Pydantic Request Validation",
        "Pydantic BaseModel detected."
    ),

    (
        "API-005",
        Severity.MEDIUM,
        re.compile(r"HTTPException", re.IGNORECASE),
        "HTTP Error Handling",
        "HTTPException is used."
    ),

    (
        "API-006",
        Severity.LOW,
        re.compile(r"response_model", re.IGNORECASE),
        "Response Model Defined",
        "FastAPI response_model is configured."
    ),

    (
        "API-007",
        Severity.LOW,
        re.compile(r"status_code", re.IGNORECASE),
        "Status Code Specified",
        "Explicit status code detected."
    ),

    (
        "API-008",
        Severity.MEDIUM,
        re.compile(r"tags\s*=", re.IGNORECASE),
        "OpenAPI Tags Configured",
        "Endpoint tags detected."
    ),

    (
        "API-009",
        Severity.MEDIUM,
        re.compile(r"summary\s*=", re.IGNORECASE),
        "Endpoint Summary",
        "OpenAPI summary detected."
    ),

    (
        "API-010",
        Severity.HIGH,
        re.compile(r"CORSMiddleware", re.IGNORECASE),
        "CORS Middleware Configured",
        "CORSMiddleware detected."
    ),

    (
        "API-011",
        Severity.MEDIUM,
        re.compile(r"\bRequest\b", re.IGNORECASE),
        "Request Object Usage",
        "FastAPI Request object detected."
    ),

    (
        "API-012",
        Severity.LOW,
        re.compile(r"\bResponse\b", re.IGNORECASE),
        "Response Object Usage",
        "FastAPI Response object detected."
    ),

    (
        "API-013",
        Severity.HIGH,
        re.compile(r"rate.?limit|Limiter|slowapi", re.IGNORECASE),
        "Rate Limiting Configured",
        "Rate limiting implementation detected."
    ),

    (
        "API-014",
        Severity.MEDIUM,
        re.compile(r"middleware", re.IGNORECASE),
        "Middleware Implemented",
        "Middleware registration detected."
    ),

    (
        "API-015",
        Severity.LOW,
        re.compile(r"openapi_url", re.IGNORECASE),
        "OpenAPI Customization",
        "OpenAPI URL customization detected."
    ),
]


def check_api(file_path: str) -> list[Finding]:

    findings: list[Finding] = []

    try:
        code = Path(file_path).read_text(
                    encoding="utf-8",
                    errors="ignore"
                    )
    except Exception:
        return findings

    endpoint_found = False
    lines = code.splitlines()
    for rule_id, severity, pattern, title, description in RULES:
        matched = False
        for line_no, line in enumerate(lines, start=1):
            
                if not pattern.search(line):
                    continue

                if rule_id == "API-001":
                    endpoint_found = True

                findings.append(
                    Finding(
                        id=rule_id,
                        title=title,
                        severity=severity,
                        category=Category.API,
                        description=description,
                        recommendation="Review this implementation.",
                        file=file_path,
                        line=line_no,
                        confidence=0.98,
                        evidence=[
                            Evidence(
                                file=file_path,
                                line=line_no,
                                snippet=line.strip(),
                                reason=description,
                            )
                        ],
                    )
                )
        matched = True
        break
    if matched:
        pass
    if endpoint_found:

        if "Depends(" not in code:
            findings.append(
                Finding(
                    id="API-101",
                    title="Missing Dependency Injection",
                    severity=Severity.HIGH,
                    category=Category.API,
                    description="Depends() not found.",
                    recommendation="Use Depends() for authentication.",
                    file=file_path,
                    line=1,
                    confidence=0.95,
                    
                )
            )

        if "BaseModel" not in code:
            findings.append(
                Finding(
                    id="API-102",
                    title="Missing Request Validation",
                    severity=Severity.HIGH,
                    category=Category.API,
                    description="BaseModel not found.",
                    recommendation="Use Pydantic BaseModel.",
                    file=file_path,
                    line=1,
                    confidence=0.95,
                    
                )
            )

        if "HTTPException" not in code:
            findings.append(
                Finding(
                    id="API-103",
                    title="Missing HTTP Error Handling",
                    severity=Severity.HIGH,
                    category=Category.API,
                    description="HTTPException not found.",
                    recommendation="Use HTTPException for API errors.",
                    file=file_path,
                    line=1,
                    confidence=0.95,
                    
                )
            )

        if "response_model" not in code:
            findings.append(
                Finding(
                    id="API-104",
                    title="Missing Response Model",
                    severity=Severity.HIGH,
                    category=Category.API,
                    description="response_model not defined.",
                    recommendation="Define response_model for endpoints.",
                    file=file_path,
                    line=1,
                    confidence=0.95,
                    
                )
            )

    return findings