# Option strike classification (research-only)

`Backend.application.options.strike_selection` classifies CE/PE contracts using
spot-relative configurable thresholds, and evaluates a conservative eligibility
filter for quote freshness, bid/ask spread, open interest and delta.

This module is **not wired to order placement**. The returned `eligible` flag
means only that supplied market-data fields pass configured screening thresholds;
it is **not** a buy/sell signal or authorization to trade.

Default thresholds: ATM within 0.15%, near ATM within 0.5%, deep ITM/OTM
from 2%. These are conventions, not exchange-defined categories.
The default filter permits ATM, near ATM and ITM, requires OI >= 1000,
spread <= 5%, absolute delta 0.25–0.85 and quotes <= 30 seconds old.

Before integrating with production execution, verify contract identity and
expiry, exchange lot sizes, live quote provenance and timestamps, and run
historical replay/paper trading with slippage and fees. Preserve existing
risk gates and never bypass broker reconciliation.
