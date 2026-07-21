SEVERITY_WEIGHT = {
    "CRITICAL":95,
    "HIGH":80,
    "MEDIUM":60,
    "LOW":30
}


def calculate_confidence(finding):

    severity = finding.get(
        "severity",
        "LOW"
    ).upper()


    confidence = SEVERITY_WEIGHT.get(
        severity,
        20
    )


    issue = str(
        finding.get("issue","")
    ).lower()


    if "secret" in issue:
        confidence += 15

    if "password" in issue:
        confidence += 10

    if finding.get("line"):
        confidence += 5


    return min(
        confidence,
        100
    )



def enrich_confidence(findings):

    for finding in findings:

        finding["confidence"] = (
            calculate_confidence(
                finding
            )
        )

    return findings