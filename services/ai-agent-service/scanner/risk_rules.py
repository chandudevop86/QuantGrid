RULE_SEVERITY = {

    "SECURITY-001": {
        "severity": "HIGH",
        "min_confidence": 90
    },

    "DB-001": {
        "severity": "MEDIUM",
        "min_confidence": 70
    },

}


def apply_rule_intelligence(finding):

    rule_id = finding.get("id")

    rule = RULE_SEVERITY.get(rule_id)

    if not rule:
        return finding


    finding["severity"] = rule["severity"]


    if finding.get("confidence", 0) < rule["min_confidence"]:
        finding["severity"] = "LOW"


    return finding



def apply_risk_rules(findings):

    return [
        apply_rule_intelligence(f)
        for f in findings
    ]