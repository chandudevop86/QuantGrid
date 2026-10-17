# NIFTY automatic CE/PE — safety implementation status

**State: paper candidate selection only; no live-money execution authorization.**

## Implemented in this branch

- A deterministic NIFTY ATM CE/PE resolver accepts only explicitly supplied, provider-backed Dhan option-chain rows. It checks side, underlying, provider, data-quality status, receipt-time age (maximum 120 seconds), expiry, option security ID, positive volume, valid bid/ask, and maximum 3% bid/ask spread. Any missing or degraded input returns **No Trade** via an exception.
- The durable broker submission correlation ID is shortened to fit Dhan Super Order's 30-character limit. The durable duplicate/unknown-order handling is unchanged.
- The existing live-analysis worker supports an **opt-in paper-only candidate check** using `QUANTGRID_AUTO_OPTION_PAPER_CANDIDATES=true`. The candidate response includes `execution_approved=false`. With this flag, the worker deliberately **does not** simulate a NIFTY spot trade as if a CE/PE option had filled, nor does it submit a broker order.
- This branch does not change live authorization flags, position risk limits, deployment, credentials, or production broker access.

## Important limitation

The current option-chain `updated_at` field indicates when QuantGrid assembled the response, **not necessarily the exchange timestamp of an option quote**. This first gate is **not sufficient for live execution**. Real fill simulation or order submission must use a verified per-contract quote timestamp and executable bid/ask.

## Remaining acceptance gates before implementing live auto-trading

1. Verify Dhan API entitlement, exchange timestamp, daily instrument master, exact expiry/security ID, tick size and **current** lot size for every CE/PE selection.
2. Build option-premium-specific sizing, option entry/SL/target geometry, bid/ask slippage/cost modelling, max premium, available broker cash, and risk limits. Spot-index stop prices must never be reused as option-premium stops.
3. Integrate Dhan's protected Super Order path into the **actual** lifecycle, verify broker-native stop-loss and target acknowledgements and coverage for partial fills, and prohibit unprotected live exposure.
4. Implement restart recovery, live reconciliation of fills/positions/protective legs, no ambiguous resend, alerting, and live kill switch drills.
5. Build an audited automatic live worker that goes through the same authenticated execution gates and cannot bypass No Trade, user entitlement, or risk limits.
6. Complete mocked broker failure-injection tests, prolonged realistic forward-paper results, broker/regulatory onboarding and separate owner review. Only after approval may a supervised, separately limited live pilot be considered.

## Validation

Focused pure-selector checks can be run with:

```bash
PYTHONPATH=services/trading-service python -m pytest services/tests/test_option_contract_resolver.py -q
PYTHONPATH=services/trading-service python -m pytest services/tests/test_nifty_option_paper_candidate.py services/tests/test_broker_submission_intent.py -q
```

The repository's full CI workflow includes Ruff, Python compilation, grouped backend tests, security checks, frontend, Docker and Terraform. Do not merge without required green checks and review.

## Rollback

Revert the pull request; all opt-in candidate behavior disappears and the worker returns to its existing paper-only behavior. Do not revert the shorter correlation ID if Dhan Super Orders have been accepted with the new compatible format.
