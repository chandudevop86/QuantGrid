from datetime import datetime, timezone
from typing import Any

from .config import (
    MAX_ENTRY_PRICE_DEVIATION,
    MAX_PRICE_AGE_SECONDS,
    MAX_SPREAD_PERCENT,
    DEFAULT_TICK_SIZE,
)


def _market_price_fresh(
    price_response: dict[str, Any],
    max_age_seconds: int = MAX_PRICE_AGE_SECONDS,
) -> bool:
    """
    Validate live market price freshness.
    """

    try:
        timestamp = price_response.get("timestamp")

        if not timestamp:
            return False

        price_time = datetime.fromisoformat(
            str(timestamp)
        )

        if price_time.tzinfo is None:
            price_time = price_time.replace(
                tzinfo=timezone.utc
            )

        age = (
            datetime.now(timezone.utc)
            - price_time
        ).total_seconds()

        return age <= max_age_seconds

    except Exception:
        return False



def _valid_tick(
    price: float,
    tick_size: float = DEFAULT_TICK_SIZE,
) -> bool:
    """
    Validate exchange tick size.
    """

    try:
        rounded = round(
            price / tick_size
        ) * tick_size

        return abs(price - rounded) < 0.000001

    except Exception:
        return False



def _spread_valid(
    price_response: dict[str, Any],
) -> bool:
    """
    Validate bid ask spread.
    """

    try:
        bid = float(
            price_response.get("bid")
        )

        ask = float(
            price_response.get("ask")
        )

        if bid <= 0 or ask <= 0:
            return False


        spread = (
            ask - bid
        ) / bid


        return spread <= MAX_SPREAD_PERCENT


    except Exception:
        return True



def market_aligned(
    signal,
    get_price,
) -> tuple[bool, str | None]:
    """
    Validate signal price against live market.

    Returns:
        (True,None) if valid
        (False,reason) otherwise
    """

    try:
        price_response = get_price(
            signal.symbol
        )

    except Exception:
        return False, "Unable to fetch market price"


    source = str(
        price_response.get(
            "source",
            ""
        )
    ).lower()


    if source in {
        "sample-fallback",
        "stored-live-cache",
    }:
        return False, (
            "Non-live market price source"
        )


    if not _market_price_fresh(
        price_response
    ):
        return False, (
            "Market price is stale"
        )


    if not _spread_valid(
        price_response
    ):
        return False, (
            "Bid ask spread too high"
        )


    try:
        market_price = float(
            price_response.get("price")
        )

        entry_price = float(
            signal.entry_price
        )

    except Exception:
        return False, (
            "Invalid price format"
        )


    if market_price <= 0:
        return False, (
            "Invalid market price"
        )


    if not _valid_tick(
        entry_price
    ):
        return False, (
            "Entry price violates tick size"
        )


    deviation = abs(
        entry_price - market_price
    ) / market_price


    if deviation > MAX_ENTRY_PRICE_DEVIATION:
        return False, (
            f"Entry deviation too high "
            f"{deviation:.2%}"
        )


    return True, None