def normalize_mode(mode: str) -> str:
    if not mode:
        return "live"
    return mode.lower().strip()


def recent_true(values, index: int | None = None, lookback: int = 3):
    if index is None:
        return any(values[-lookback:])

    start = max(0, int(index) - int(lookback) + 1)
    window = values.iloc[start:int(index) + 1] if hasattr(values, "iloc") else values[start:int(index) + 1]
    for offset in range(len(window) - 1, -1, -1):
        if bool(window.iloc[offset] if hasattr(window, "iloc") else window[offset]):
            return start + offset

    return None
