def adjust_severity(finding):

    confidence = finding.get(
        "confidence",
        0
    )

    severity = finding.get(
        "severity",
        "LOW"
    ).upper()


    # downgrade uncertain findings

    if confidence < 70:

        if severity == "HIGH":
            finding["severity"] = "MEDIUM"

        elif severity == "MEDIUM":
            finding["severity"] = "LOW"


    return finding



def adjust_findings(findings):

    updated = []

    for finding in findings:
        updated.append(
            adjust_severity(finding)
        )

    return updated