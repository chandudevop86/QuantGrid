from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from Backend.application.fno_narrative_service import run_fno_narrative


_LAST_SNAPSHOTS: dict[str, dict[str, Any]] = {}


def build_market_copilot(symbol: str = "NIFTY") -> dict[str, Any]:
    symbol = symbol.upper()
    signal = run_fno_narrative(symbol)
    signal_payload = signal.model_dump() if hasattr(signal, "model_dump") else signal.dict()
    inputs = dict(signal_payload.get("inputs_snapshot") or {})
    current_snapshot = _snapshot(signal_payload, inputs)
    previous = _LAST_SNAPSHOTS.get(symbol)
    _LAST_SNAPSHOTS[symbol] = current_snapshot

    return {
        "module": "market_copilot",
        "symbol": symbol,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": _summary(signal_payload),
        "signal_explanation": _signal_explanation(signal_payload),
        "bullish_reasons": _bullish_reasons(signal_payload, inputs),
        "bearish_reasons": _bearish_reasons(signal_payload, inputs),
        "invalidation_level": signal_payload.get("key_levels", {}).get("invalidation"),
        "invalidation_text": signal_payload.get("invalidation"),
        "confidence_score": signal_payload.get("confidence"),
        "market_regime": signal_payload.get("market_regime"),
        "market_narrative": _market_narrative(signal_payload, inputs),
        "what_changed": _what_changed(previous, current_snapshot),
        "guardrails": [
            "Copilot explains context only; it does not issue blind buy/sell calls.",
            "Act only after your strategy, risk gate, and execution mode confirm the setup.",
            "Paper mode remains separate from live trading.",
        ],
        "raw_signal": signal_payload,
    }


def reset_market_copilot_state() -> None:
    _LAST_SNAPSHOTS.clear()


def _snapshot(signal: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "signal": signal.get("signal"),
        "confidence": signal.get("confidence"),
        "market_regime": signal.get("market_regime"),
        "spot_price": inputs.get("spot_price"),
        "pcr": inputs.get("pcr"),
        "india_vix": inputs.get("india_vix"),
        "fii_cash": inputs.get("fii_cash"),
        "fii_index_futures": inputs.get("fii_index_futures"),
        "invalidation": signal.get("key_levels", {}).get("invalidation"),
    }


def _summary(signal: dict[str, Any]) -> str:
    action = str(signal.get("signal") or "NO_TRADE")
    regime = signal.get("market_regime") or "Unknown"
    confidence = signal.get("confidence")
    if action == "NO_TRADE":
        stance = "Wait mode"
    elif action == "BUY_CE":
        stance = "Upside scenario"
    elif action == "BUY_PE":
        stance = "Downside scenario"
    else:
        stance = "Scenario watch"
    return f"{stance}: {regime} context with {confidence}% confidence. This is an explanation, not an order instruction."


def _signal_explanation(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario": _scenario_label(str(signal.get("signal") or "NO_TRADE")),
        "reason": signal.get("reason"),
        "why_now": signal.get("why_now"),
        "patterns": signal.get("detected_patterns") or [],
        "risk_plan": signal.get("risk_plan") or {},
        "expiry_warning": signal.get("expiry_warning"),
        "option_context": signal.get("option_strike_suggestion"),
    }


def _bullish_reasons(signal: dict[str, Any], inputs: dict[str, Any]) -> list[str]:
    reasons = []
    patterns = set(signal.get("detected_patterns") or [])
    if "Resistance breakout" in patterns:
        reasons.append("Spot is attempting or holding above option-chain resistance.")
    if "Put writing" in patterns:
        reasons.append("Put-side OI change suggests support building below spot.")
    if "Short covering" in patterns:
        reasons.append("Call-side OI reduction points to short covering pressure.")
    if _positive(inputs.get("fii_cash")) or _positive(inputs.get("fii_index_futures")):
        reasons.append("Institutional cash or index-futures flow is supportive.")
    if _positive(inputs.get("gift_nifty_change_pct")) or _positive(inputs.get("global_market_cues")):
        reasons.append("External market cues are supportive.")
    return reasons or ["No strong bullish confirmation is currently visible."]


def _bearish_reasons(signal: dict[str, Any], inputs: dict[str, Any]) -> list[str]:
    reasons = []
    patterns = set(signal.get("detected_patterns") or [])
    if "Support breakdown" in patterns:
        reasons.append("Spot is attempting or holding below option-chain support.")
    if "Call writing" in patterns:
        reasons.append("Call-side OI change suggests resistance building above spot.")
    if "Long unwinding" in patterns:
        reasons.append("Futures premium and price action point to long unwinding.")
    if _negative(inputs.get("fii_cash")) or _negative(inputs.get("fii_index_futures")):
        reasons.append("Institutional cash or index-futures flow is cautious.")
    if _negative(inputs.get("gift_nifty_change_pct")) or _negative(inputs.get("global_market_cues")):
        reasons.append("External market cues are cautious.")
    if "Fake breakout" in patterns or "Fake breakdown" in patterns:
        reasons.append("False-break risk is elevated, so directional conviction is weaker.")
    return reasons or ["No strong bearish confirmation is currently visible."]


def _market_narrative(signal: dict[str, Any], inputs: dict[str, Any]) -> str:
    return (
        f"{signal.get('market_regime')} regime. {signal.get('reason')} "
        f"PCR {inputs.get('pcr', '-')}, VIX {inputs.get('india_vix', '-')}, "
        f"spot {inputs.get('spot_price', '-')}. {signal.get('why_now')}"
    )


def _what_changed(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if previous is None:
        return ["First copilot snapshot loaded; future refreshes will compare signal, confidence, regime, spot, PCR, VIX, and invalidation."]
    changes = []
    labels = {
        "signal": "Scenario",
        "confidence": "Confidence",
        "market_regime": "Regime",
        "spot_price": "Spot",
        "pcr": "PCR",
        "india_vix": "India VIX",
        "fii_cash": "FII cash",
        "fii_index_futures": "FII index futures",
        "invalidation": "Invalidation",
    }
    for key, label in labels.items():
        before = previous.get(key)
        after = current.get(key)
        if before != after:
            changes.append(f"{label} changed from {_display(before)} to {_display(after)}.")
    return changes or ["No material copilot inputs changed since the last refresh."]


def _scenario_label(signal: str) -> str:
    if signal == "BUY_CE":
        return "Upside option scenario if confirmation remains valid"
    if signal == "BUY_PE":
        return "Downside option scenario if confirmation remains valid"
    return "No-trade / wait scenario"


def _positive(value: Any) -> bool:
    parsed = _number(value)
    return parsed is not None and parsed > 0


def _negative(value: Any) -> bool:
    parsed = _number(value)
    return parsed is not None and parsed < 0


def _number(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _display(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
