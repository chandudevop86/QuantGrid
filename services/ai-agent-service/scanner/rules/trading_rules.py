import os
import re


ORDER_FILES = [
    "broker",
    "execution",
    "order",
    "oms",
    "position",
    "trade",
]


ORDER_FUNCTIONS = [
    "place_order",
    "submit_order",
    "execute_order",
    "buy",
    "sell",
    "market_order",
    "limit_order",
]


RISK_CONTROLS = [
    "stop_loss",
    "risk",
    "risk_manager",
    "max_loss",
    "position_limit",
    "max_position",
    "quantity_limit",
    "validate_order",
]


def check_trading(file_path: str, code: str):

    findings = []

    filename = os.path.basename(file_path).lower()

    if not any(name in filename for name in ORDER_FILES):
        return findings

    code_lower = code.lower()

    has_order = any(func in code_lower for func in ORDER_FUNCTIONS)

    if not has_order:
        return findings

    # ----------------------------------------------------
    # TRADE-001
    # Missing risk controls
    # ----------------------------------------------------

    has_risk = any(ctrl in code_lower for ctrl in RISK_CONTROLS)

    if not has_risk:

        findings.append({
            "id": "TRADE-001",
            "severity": "HIGH",
            "issue": "Live order execution path lacks visible risk control",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-002
    # Missing stop loss
    # ----------------------------------------------------

    if "stop_loss" not in code_lower:

        findings.append({
            "id": "TRADE-002",
            "severity": "HIGH",
            "issue": "Order execution without stop-loss protection",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-003
    # Position sizing
    # ----------------------------------------------------

    sizing_keywords = [
        "position_size",
        "quantity",
        "qty",
        "lot_size",
        "max_quantity",
    ]

    if not any(k in code_lower for k in sizing_keywords):

        findings.append({
            "id": "TRADE-003",
            "severity": "MEDIUM",
            "issue": "No visible position sizing logic",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-004
    # Order validation
    # ----------------------------------------------------

    validation_keywords = [
        "validate_order",
        "validate",
        "pre_trade",
    ]

    if not any(k in code_lower for k in validation_keywords):

        findings.append({
            "id": "TRADE-004",
            "severity": "MEDIUM",
            "issue": "Order validation not detected",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-005
    # Circuit breaker
    # ----------------------------------------------------

    breaker_keywords = [
        "circuit_breaker",
        "kill_switch",
        "emergency_stop",
    ]

    if not any(k in code_lower for k in breaker_keywords):

        findings.append({
            "id": "TRADE-005",
            "severity": "HIGH",
            "issue": "Trading circuit breaker not implemented",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-006
    # Paper trading mode
    # ----------------------------------------------------

    if (
        "paper_trade" not in code_lower
        and "paper_mode" not in code_lower
        and "simulation" not in code_lower
    ):

        findings.append({
            "id": "TRADE-006",
            "severity": "LOW",
            "issue": "Paper trading mode not detected",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-007
    # Confirmation
    # ----------------------------------------------------

    if (
        "confirm_order" not in code_lower
        and "confirm_trade" not in code_lower
        and "user_confirmation" not in code_lower
    ):

        findings.append({
            "id": "TRADE-007",
            "severity": "LOW",
            "issue": "Trade confirmation step not detected",
            "file": file_path,
        })

    # ----------------------------------------------------
    # TRADE-008
    # Retry loop
    # ----------------------------------------------------

    if re.search(r"while\s+true", code, re.IGNORECASE):

        findings.append({
            "id": "TRADE-008",
            "severity": "MEDIUM",
            "issue": "Potential infinite retry loop in trading execution",
            "file": file_path,
        })

    return findings