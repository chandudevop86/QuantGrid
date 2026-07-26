def _safe_float(value: Any) -> float | None:
    """
    Safely convert a value to float.

    Returns:
        float value if conversion succeeds.
        None otherwise.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


