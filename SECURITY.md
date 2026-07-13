# Security Policy

## Supported Version

Only the current `main` branch and the latest tagged release receive security fixes.

## Reporting a Vulnerability

Open a private security advisory or contact the repository owner directly. Do not file public issues for exploitable vulnerabilities.

## Security Requirements

- No default credentials.
- No committed secrets.
- `QUANTGRID_AUTH_SECRET` must be at least 32 characters.
- Production must use Postgres; SQLite is blocked.
- CORS origins must be explicitly configured in production.
- Live trading remains disabled unless broker credentials are configured and live mode is intentionally enabled.
- Execution and admin actions must write audit logs.

## Browser Token Threat Decision

QuantGrid currently uses bearer tokens in browser `sessionStorage`, not persistent
`localStorage`. Legacy local tokens are migrated once and removed. This limits token
persistence to the active tab/session, but JavaScript-accessible tokens can still be
read by a successful same-origin XSS attack.

Risk controls are therefore layered: restrictive CSP is emitted by both Nginx and
the API, scripts are limited to same-origin assets, framing and object embedding are
blocked, token lifetimes are enforced server-side, and logout clears session tokens.
Do not add third-party scripts or relax `script-src` without security review.

HttpOnly, Secure, SameSite cookies remain the preferred future hardening path. That
migration requires CSRF protection and coordinated API/client authentication changes;
until completed, session storage is an explicit accepted residual risk rather than an
unexamined persistence choice.
