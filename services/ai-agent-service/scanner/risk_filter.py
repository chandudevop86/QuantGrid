def filter_actionable_findings(findings):

    return [
        f
        for f in findings
        if f.get(
            "confidence",
            0
        ) >= 50
    ]
