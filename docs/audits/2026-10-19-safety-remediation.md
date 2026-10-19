# QuantGrid safety remediation — 2026-10-19

## Changes proposed

- Live position exits claim a persistent, compare-and-set `pending_exit_correlation_id` before broker network I/O.
- Unknown broker outcomes (no order ID, transport timeout, crash/restart after claim) **do not trigger another broker submission**.
- A pending exit ID is queried; only matching, authoritative broker-fill evidence may close a local position.
- Rejections and unconfirmed exit status preserve the exit claim until manual broker reconciliation; no automatic second exit order.
- Paper and live exit monitoring are separated by position execution mode; an API call cannot exit a position through the wrong mode.
- The risk summary deduplicates paper closes mirrored in the position ledger by broker order ID, preferring cost-adjusted paper P&L; Indian session dates drive daily figures.
- Live positions are included in daily entry counts despite never appearing in the paper-trade ledger.

## Deliberately not included / still blocked

- **Do not enable live flags**: `QUANTGRID_ENABLE_LIVE_TRADING=false`, `QUANTGRID_LIVE_MONEY_APPROVED=false`, `BROKER_LIVE_ENABLED=false`.
- This patch does **not** certify the Dhan broker-native Super Order stop leg, actual fills, account reconciliation, regulatory permission, or live money.
- A claimed exit without a broker ID is an **operator incident**. Verify broker order book, correlation ID, partial fills, net position and protection before any manual release. Do not clear the marker on timeout or inferred `not_found`.
- The daily risk summary combines local paper and live records for conservatism. It is not an authoritative real-money account risk ledger or broker contract-note reconciliation.
- Legacy records without matching broker IDs cannot be deduplicated reliably. Production should not enable live without ledger migration and authoritative broker account-risk proof.
- Current option selector is advisory and option premiums are not simulated as real executions.
- The production deploy workflow remains blocked if tracked server files are modified. Inspect `git status --short` and preserve any local changes; do not automatically reset/clean the server.
- Verify out-of-sample causal backtests, vendor quote provenance, 30 paper-market sessions, backup and restore, independent review, live exit failure injection and release evidence before any further trading capability changes.

## Validation before merge

Run `python -m pytest services/tests/test_trade_exit_engine.py services/tests/test_risk_ledger_dedup.py services/tests/test_risk_gate_and_journal.py services/tests/test_full_paper_trade_lifecycle.py -q` with the project's test environment and inspect all GitHub CI/Security/CodeQL checks. Mocked tests do not certify real broker behavior.

## Deployment incident reference

Prior main production attempts through AWS SSM returned `Deployment refused: tracked changes exist on the production server.` The remedy is a reviewed server-side change reconciliation, **not** weakening the deployment safety gate.
