# Option buyer: paper ledger and live-data testing

The `paper_order_ledger.record_verified_paper_buy` function atomically
records one paper option order, its paper position and audit event in a
single SQLite transaction. Idempotency is scoped by actor ID and request key.
Conflicting reuse is rejected. It does not call any broker.

This ledger is NOT YET wired into the HTTP paper-order endpoint. That endpoint
continues to return HTTP 503 until server-authoritative exchange lot size,
per-quote timestamp, capital/position checks and an authenticated actor ID
are verified and passed to the ledger. Do not trust browser-supplied prices,
Greeks, security IDs or lot sizes.

Live-market testing is supported conceptually through the read-only Dhan
option-chain preview; real-money order submission is NOT enabled. A real
broker execution test requires separate explicit activation, reconciled
broker state, kill switch and independent order risk review.

Tests added: `services/tests/options/test_paper_order_ledger.py`.
No CI run or deployment has been verified.
