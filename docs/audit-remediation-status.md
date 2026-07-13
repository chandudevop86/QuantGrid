# Audit Remediation Status

Date: 2026-07-13

## Completed

- Canonical typed five-section dashboard summary and compatibility route.
- Five-section decision dashboard with explicit No Trade and System Trust surfaces.
- Genuine timeframe separation and fallback/sample sources blocked from decision eligibility.
- Cross-row candle and option-chain integrity validation.
- Shared frontend operations status provider; legacy duplicate polling removed.
- Strategies and Live Analysis duplicate pages consolidated.
- Frontend behavioral, accessibility, and Playwright smoke coverage.
- CSP and sanitized database-health responses.
- Session-scoped authentication token storage; persistent legacy tokens are deleted without reuse.
- Synthetic option-chain rows remain hidden and sample-only unused strategy UI was removed.
- Backtests precompute strategy indicators once instead of recalculating them for every candle prefix.
- Schema migration ledger owns upgrades; SQLAlchemy metadata bootstrap runs only before the ledger exists.
- Frontend Vite 6/Vitest 4 upgrade completed; npm and Python dependency audits report zero vulnerabilities.

## Requires deployment evidence

These items cannot be truthfully completed from repository code alone:

- Live provider quality probe during Indian market hours.
- Redis, WebSocket, broker session, `/health`, and authenticated `/metrics` checks on the deployed host.
- Thirty paper-market sessions with positive net expectancy after all costs.
- Login, admin, execution, and reconciliation audit-event verification.
- Staging rollback exercise.
- Backup creation and database restore exercise.

Live trading remains disabled until this operational evidence is recorded and approved.

## Deferred architecture decision

HttpOnly authentication cookies would further reduce token exposure, but require a coordinated CSRF, proxy, API-client, and mobile-client migration. Current controls use tab-scoped storage, strict CSP, short token expiry, role validation, and removal of persistent legacy tokens.
