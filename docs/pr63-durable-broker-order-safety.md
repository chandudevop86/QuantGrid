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
