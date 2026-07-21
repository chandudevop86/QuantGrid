import hashlib


def normalize_finding(finding):

    key = "|".join(
        [
            str(finding.get("id")),
            str(finding.get("file")),
            str(finding.get("line")),
            str(finding.get("issue")),
        ]
    )

    fingerprint = hashlib.sha256(
        key.encode()
    ).hexdigest()

    finding["fingerprint"] = fingerprint

    return finding



def deduplicate_findings(findings):

    unique = {}

    for finding in findings:

        finding = normalize_finding(finding)

        unique[
            finding["fingerprint"]
        ] = finding


    return list(unique.values())