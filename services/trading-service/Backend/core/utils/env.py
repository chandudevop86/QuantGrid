import os


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def float_env(
    name: str,
    default: float
) -> float:
    try:
        return float(
            os.getenv(
                name,
                default
            )
        )

    except (
        TypeError,
        ValueError
    ):
        return default


def int_env(
    name: str,
    default: int
) -> int:
    try:
        return int(
            os.getenv(
                name,
                default
            )
        )

    except (
        TypeError,
        ValueError
    ):
        return default