# Deployment Readiness Verification

Date: 2026-07-13

## Verified in the repository

- Production configuration rejects SQLite.
- The secret scanner reports no obvious committed secrets or default credentials.
- Docker Compose v2 is available and both `docker-compose.yml` and `docker-compose.app.yml` render successfully with temporary verification values.
- Backend, frontend, Redis, Postgres, and Kafka published ports are bound to `127.0.0.1` in checked-in Compose configuration.
- Deployment and Jenkins shell scripts pass `bash -n` using Git Bash.
- Nginx configuration contains TLS, HSTS, CSP, frame, MIME-sniffing, referrer, and permissions-policy headers.
- The application stack runs a dedicated `migrate` service before backend startup.
- Production frontend npm dependencies report zero known vulnerabilities.
- Python service requirements report zero known vulnerabilities through `pip-audit`.
- Frontend unit, accessibility, production build, and Playwright landing smoke checks are available as npm scripts.

## Requires staging or production evidence

- Set and verify `QUANTGRID_ENV=production`, `QUANTGRID_AUTH_SECRET`, `DATABASE_URL`, and `CORS_ALLOWED_ORIGINS` in the deployment secret store.
- Run `python scripts/market_data_quality_probe.py --require-execution` during Indian market hours with the configured live provider.
- Verify Redis, `/health`, `/metrics`, WebSocket upgrade, and broker session health on the deployed host.
- Complete the paper-execution smoke test and retain at least 30 market sessions of journal evidence.
- Verify audit events for login, admin, and execution actions.
- Test rollback, backup creation, and database restore in staging.
- Keep live trading disabled until every operational item above is evidenced and approved.

## Dependency review

- Frontend production and development dependencies report zero known npm vulnerabilities after the Vite 6 and Vitest 4 maintenance upgrade.
- Python service requirements report zero known vulnerabilities through `pip-audit`.
