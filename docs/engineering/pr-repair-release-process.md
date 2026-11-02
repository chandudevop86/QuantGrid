# QuantGrid systematic PR repair and release process

## Stage 1: detect and classify
1. Master agent collects latest head SHA, base branch, draft state, CI, Security, CodeQL, and review status for each open PR.
2. Block on failed, cancelled, queued or missing required checks. Never infer green from an older commit.
3. Categorize by impact: security/dependency, infrastructure, data, research, trading risk/execution, regulatory/client, and documentation.
4. Cluster shared failures by root cause before editing dozens of branches. Record finding, evidence, owner and severity.

## Stage 2: fix safely
1. Fix common base-branch vulnerabilities in a dedicated small PR, including matching manifest and lockfile.
2. Validate lockfile integrity with npm ci; run frontend tests, backend unit tests, static analysis, dependency/secret scans and CodeQL.
3. Rebase or update dependent branches against fixed main, resolve conflicts and rerun all required checks for the NEW head SHA.
4. Fix individual CI errors with focused tests. Do not weaken checks or hide findings.
5. Any live-trading, tenant isolation, broker reconciliation or regulatory PR requires specialist review even when checks are green.

## Stage 3: approvals and merge
- Auto: read-only checks, diagnostics, draft PRs, test-only fixes.
- Manual: merges, production deploys, client access, broker credentials, risk changes, security-critical fixes and compliance policy changes.
- Require explicit authenticated owner approval, all checks green on latest SHA, code review, correct base, no unresolved critical finding and rollback plan.
- Merge independent low-risk changes first; stacked PRs only after parent PRs. Confirm merge response and main branch checks.

## Stage 4: staging and production
- Build immutable artifact, deploy to staging, verify API contracts, DB migration dry run, observability, security and rollback.
- Release production only after approval and verified maintenance window.
- Run smoke checks and incident monitoring; automatically rollback only where pre-authorized and proven safe.
- Keep live trading disabled unless independent legal, broker, exchange and financial safeguards have passed.

## Stage 5: operate and learn
- Monitor network, DB, security, market data freshness, worker lag, CI and certificate expiry.
- Record alert deduplication, severity, timestamps, assigned owner, incident postmortem, follow-up tests and closure evidence.
- Weekly security review; monthly backup restoration and dependency review; quarterly disaster recovery exercise.
- Track SEBI/NSE/MCA changes with dated official sources and human applicability review.
- Never claim 24/7 availability from GitHub Actions alone; use an always-running monitored worker and alert delivery.

## Current repair priority
1. PR #179: CVE-2026-116689 follow-redirects upgrade 1.16.1 to 1.16.2.
2. Rerun Security across dependent PRs after merge/rebase.
3. PR #171: investigate failed CI job and fix root cause.
4. Review stacked live reconciliation PRs #162–#167 for account/order identity binding and transactional reservation.
5. Review agent and compliance PRs #168–#178; integrate with actual telemetry, provider notifications and approval records.
