# QuantGrid client handover

## Product boundary

QuantGrid is decision-support software. The accepted production baseline is paper mode. Live execution requires a separate security, broker, compliance, and client-approval release gate. No screen, score, signal, or alert is a profit promise.

## Handover package

- Release commit/tag and signed release-evidence record.
- Production environment owner and secrets-vault owner (never the secret values).
- DNS/TLS owner, renewal method, and expiry monitoring.
- Database backup location, retention policy, and latest restore-drill record.
- Monitoring dashboards, alert destinations, and on-call escalation contacts.
- Admin, operator, trader, analyst, and viewer access matrix.
- UAT acceptance record and known-limitations acknowledgement.

## Operator walkthrough

1. Confirm TLS, `/health`, database, Redis, worker, market-data age, and paper mode.
2. Sign in with each representative role and verify subscription gates.
3. Run a paper analysis, paper order, position update, alert, and audit-log review.
4. Create and verify a backup; demonstrate restore only against a disposable target.
5. Demonstrate application rollback using the previously recorded commit.
6. Confirm incident, support, and credential-rotation contacts.

## Acceptance

The client product owner, technical owner, security owner, and delivery owner sign the UAT record. Open critical or high defects block acceptance. Medium and low defects require an owner and target date.
