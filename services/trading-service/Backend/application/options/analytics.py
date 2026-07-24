def _max_pain(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None

    def pain(candidate: dict[str, Any]) -> float:
        candidate_strike = float(candidate.get("strike") or 0)

        return sum(
            max(float(row.get("strike") or 0) - candidate_strike, 0.0)
            * float((row.get("ce") or {}).get("oi") or 0)
            +
            max(candidate_strike - float(row.get("strike") or 0), 0.0)
            * float((row.get("pe") or {}).get("oi") or 0)
            for row in rows
        )

    result = min(rows, key=pain)
    strike = result.get("strike")

    if isinstance(strike, (int, float)):
            return int(strike)

    if isinstance(strike, str):
            try:
                return int(float(strike))
            except ValueError:
                return None

    return None