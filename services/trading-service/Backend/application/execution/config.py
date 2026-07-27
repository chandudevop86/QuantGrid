from typing import Final

# Maximum age of a market quote (seconds)
MAX_PRICE_AGE_SECONDS: Final[int] = 10

# Maximum bid/ask spread (0.5%)
MAX_SPREAD_PERCENT: Final[float] = 0.005

# Exchange tick size
DEFAULT_TICK_SIZE: Final[float] = 0.05

# Maximum allowed deviation from live market price (2%)
MAX_ENTRY_PRICE_DEVIATION: Final[float] = 0.02