# PR #63 — Durable broker order safety

Status: implementation pending. This document is a plan, not a live-trading clearance.

## Acceptance criteria

- Persist a unique order submission intent and correlation ID transactionally before contacting the broker; define uniqueness across processes and restarts.
- Acquire an atomic durable claim for each logical order; never resubmit when an earlier attempt has an ambiguous outcome.
- Record broker response, timeout and reconciliation-required states durably, including audit trail.
- Resolve ambiguous outcomes against authoritative broker order/trade/position data; never infer rejection from missing or timed-out lookup.
- Reconcile safely on startup and under concurrent workers, including partial fills and cancellation races.
- Test accepted-then-timeout, repeated request, crash before/after placement, concurrent workers, delayed broker visibility, rejected orders, partial fills, and restart recovery.
- Validate in paper/sandbox with no real broker calls in CI; require passing CI and review before merge.
- Keep live trading disabled; do not deploy or change production configuration as part of this planning change.

## Implementation checklist

- [ ] Inspect existing OMS, broker adapter, order store and migrations.
- [ ] Add durable submission intent schema and atomic uniqueness/claim semantics.
- [ ] Integrate fail-closed submission lifecycle and restart reconciliation.
- [ ] Add deterministic unit/integration tests and sandbox validation.
- [ ] Review migration and rollback, pass CI, and obtain approval before deployment.

## Code review findings (2026-10-04)

- `Backend/application/order_management.py`: `_active_order_keys` is an in-memory set and cannot provide restart-safe or cross-process uniqueness. OMS explicitly delegates persistence to execution lifecycle.
- `Backend/application/order_store.py`: `create_order` commits a local order, while `get_active_order_by_key` is a read/query; a read-then-insert is not an atomic duplicate claim. `transition_order` currently has no compare-and-swap expected-state predicate.
- `Backend/application/broker_reconciliation.py`: stale pre-broker orders may be marked failed; once submission intent exists, stale intent must not be classified as definitely not sent without authoritative evidence.
- `Backend/core/database.py`: schema changes must go through `apply_versioned_migrations`, supporting production PostgreSQL and test SQLite.

## Proposed transactional design (not implemented yet)

1. Create a submission-intent table with immutable logical request key, local order ID, broker correlation ID, payload hash, created/updated timestamps, attempt count, status and last reconciliation evidence. Unique constraints on logical key and correlation ID. Do not expose secrets in evidence.
2. Acquire an atomic unique claim and commit it before network I/O. A conflict returns the existing intent and never calls broker placement. On DB failure, fail closed.
3. Before the broker call, durably mark `submission_may_have_started`. A crash after this boundary is ambiguous; never automatically retry it, even if no broker ID was saved.
4. Broker placement uses the persisted correlation ID. A timeout or unknown result stays `reconciliation_required`. Only authoritative broker evidence permits terminal transitions. No automatic resend based solely on missing lookup results.
5. Startup scans unresolved intents, correlates broker order/trade/position records, and records evidence. Partial fills remain active until quantity reconciliation completes. Manual review required for unresolved outcomes.
6. Tests must use two independent database sessions and processes where feasible, crash injection around transaction/network boundaries, duplicate concurrent calls, accepted-then-timeout, delayed visibility, partial fill and restart. Check migration/rollback and PostgreSQL uniqueness semantics; SQLite tests alone are insufficient.

**Merge gate:** implementation and tests pending. Do not merge, deploy or enable live trading on the strength of this documentation-only change.
