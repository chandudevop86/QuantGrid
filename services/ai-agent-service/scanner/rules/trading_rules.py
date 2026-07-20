def check_trading(file_path, code):

    findings=[]


    keywords = [
        "place_order",
        "submit_order",
        "buy",
        "sell"
    ]


    has_order=False

    for key in keywords:

        if key in code:
            has_order=True



    if has_order:

        if "stop_loss" not in code.lower():

            findings.append(
                {
                "id":"TRADE-001",
                "severity":"HIGH",
                "issue":"Order execution without visible stop loss handling",
                "file":file_path
                }
            )


    return findings