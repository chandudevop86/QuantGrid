def normalize_mode(mode: str) -> str:
    if not mode:
        return "live"
    return mode.lower().strip()


def recent_true(values, lookback=3):
    return any(values[-lookback:])