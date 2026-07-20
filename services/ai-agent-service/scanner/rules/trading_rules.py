import os


ORDER_FILES = [
    "broker",
    "execution",
    "order",
    "oms",
    "position",
    "trade"
]


def check_trading(file_path, code):

    findings=[]

    filename = os.path.basename(file_path).lower()


    is_execution_file = any(
        keyword in filename
        for keyword in ORDER_FILES
    )


    if not is_execution_file:
        return findings


    order_keywords = [
        "place_order",
        "submit_order",
        "execute_order",
        "buy",
        "sell"
    ]


    has_order = any(
        k in code.lower()
        for k in order_keywords
    )


    if has_order:

        risk_controls = [
            "stop_loss",
            "risk",
            "max_loss",
            "position_limit"
        ]


        has_risk = any(
            r in code.lower()
            for r in risk_controls
        )


        if not has_risk:

            findings.append(
                {
                    "id":"TRADE-001",
                    "severity":"HIGH",
                    "issue":
                    "Live order execution path lacks visible risk control",
                    "file":file_path
                }
            )


    return findings