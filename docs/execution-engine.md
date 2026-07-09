# Execution Engine Operator Guide

QuantGrid keeps live trading disabled by default. Execution safety is layered so a signal must pass decision quality, risk validation, lifecycle persistence, and broker confirmation before any position is created.

## Duplicate Order Protection

Every lifecycle order stores an `order_key` in the backend database:

`SYMBOL:SIDE:STRATEGY`

Before broker submission, the execution API checks for an existing active order with the same key. Active statuses include requested, risk approved, broker submitted, pending, open, and partially filled. Terminal statuses such as filled, cancelled, rejected, and failed release the key.

This protects against duplicate orders across process restarts and multiple API workers. The in-process OMS guard still protects concurrent submissions inside one process.

## Audit Trail

Lifecycle transitions write `order_status_transition` audit records with:

- local order id
- previous status
- next status
- broker order id
- broker status
- symbol, side, quantity
- stop loss and target
- broker response when available

Duplicate active orders are rejected before broker submission and audited with `DUPLICATE_ACTIVE_ORDER`.

## Operator Rule

If a duplicate is rejected, do not retry blindly. Inspect the existing active order, broker status, and position state first.

## Restart Recovery

Broker reconciliation also scans local lifecycle orders that are older than 30 minutes and do not have a broker order id.

- `requested` and `risk_approved` orders are marked `failed` with broker status `not_submitted`, because no broker submission was recorded.
- `broker_submitted`, `pending`, `open`, and `partially_filled` orders without a broker id are marked `needs_review`, because broker submission may have happened but the local id was lost.

This prevents stale pre-broker orders from blocking future trades forever while keeping ambiguous broker-submitted orders under human review.
