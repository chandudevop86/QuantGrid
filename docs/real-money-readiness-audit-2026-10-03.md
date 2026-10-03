# QuantGrid real-money readiness audit — 2026-10-03

**Decision gate: NOT CLEARED FOR LIVE ORDERS.** This is a code-path audit, not a successful broker integration or an end-to-end production certification. Preserve `QUANTGRID_ENABLE_LIVE_TRADING=false`, `QUANTGRID_LIVE_MONEY_APPROVED=false`, and `BROKER_LIVE_ENABLED=false`. No live broker calls were made.

## Evidence inspected
- `Backend/core/config.py`: three authorization/config gates; live broker credentials, explicit risk env variables, and Yahoo live-provider prohibition.
- `Backend/infrastructure/broker/broker_client.py`: paper broker and concrete-adapter resolver; generic `LiveBrokerClient` methods are deliberately unimplemented.
- `Backend/application/order_management.py`: broker exception/retry, correlation-ID lookup, in-memory duplicate-key set.
- `Backend/application/execution/execution_pipeline.py`: maps non-accepted OMS results to failed/rejected lifecycle state.
- `Backend/application/candle_validation.py`: session and stale-feed gates; the October 2026 holiday calendar was recently corrected.
- `services/tests/test_order_management_service.py`: current `test_oms_retries_temporary_broker_failure` expects a second broker submission without a broker lookup confirmation.
- `services/tests/test_real_money_safety_paths.py`: mocked live guardrails for approval, stale candles, HTTPS, roles, kill switch, broker circuit, and stop protection.

## Confirmed safety gap: uncertain order outcomes
`OrderManagementService._place_with_retry` retries after `place_order` raises if `_check_already_placed` returns `None`. That method also returns `None` when no correlation-ID lookup exists or when the lookup raises, rather than distinguishing *confirmed absent* from *unknown*. A broker could accept an order and then time out; a second submission can duplicate the position. The in-memory duplicate set is not a distributed or persistent guarantee. Furthermore, the execution pipeline currently transitions non-accepted OMS results to failed/rejected, potentially misrepresenting an unresolved broker submission.

### Required implementation before a live pilot
1. Introduce a distinct **UNKNOWN / RECONCILIATION_REQUIRED** order state spanning OMS, lifecycle persistence, API, and monitoring. Do not label uncertainty as definitely rejected or filled.
2. After an ambiguous submission, never automatically place another order unless a broker-supported idempotency key guarantees a single order or reconciliation supplies sufficiently authoritative proof of non-acceptance. A lookup exception or missing lookup MUST fail closed.
3. Persist correlation ID, client order ID, submission intent, and broker response before allowing retries/restarts; use a cross-process uniqueness guarantee rather than only `_active_order_keys`.
4. Reconcile orders, partial fills, net positions, and exits after timeout/restart/network loss. Quarantine unresolved submissions; alert an operator. Explicitly test cancel/replace and out-of-order events.
5. Add tests for: accepted-then-timeout, no lookup API, lookup failure, delayed broker visibility, restart between send and response, concurrent identical signals, partial fill, and recovery to reconciled terminal status.

## Other pre-live evidence gaps (not claims that features are absent)
- Verify concrete broker adapter with approved sandbox/read-only endpoints: login/token expiry, order-book, positions, margin, quantity/lot and instrument mapping, broker-native stop protection, API failures. No real orders.
- Verify a licensed trading-grade feed with exchange timestamp, gaps, disconnections, and instrument mapping. Prior deployment used Yahoo paper/demo; do not bypass its live prohibition.
- Replay risk engine, kill switch, circuit breaker, daily loss, maximum notional/position, order throttling, and protective exit controls through the actual execution pipeline.
- Verify audited user authorization, secret rotation, back-up/recovery, alerts, operational runbook, and logs redacting credentials.
- Obtain broker and regulatory onboarding confirmation for the intended retail API/algo use.
- Collect extended paper-forward evidence, including latency, fees/slippage, outages and realistic rejected/partial orders. A green unit-test suite does not prove profitability.

## Acceptance / rollout
- Gate 0: Monday current-session NIFTY/BANKNIFTY ingestion, scanner, stale rejection and paper P&L evidence.
- Gate 1: uncertain-order state and broker reconciliation fixes with adversarial CI tests.
- Gate 2: end-to-end broker/data sandbox validation and incident drills with **zero real orders**.
- Gate 3: independent review and explicit owner authorization of a separately limited, manually supervised pilot.
- Until all gates pass, no live-money flag changes and no deployment scripts that enable them.
