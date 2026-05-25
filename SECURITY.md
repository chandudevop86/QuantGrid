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
