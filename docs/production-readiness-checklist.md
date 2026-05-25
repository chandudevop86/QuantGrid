# Production Readiness Checklist

- [ ] `QUANTGRID_ENV=production`
- [ ] Strong `QUANTGRID_AUTH_SECRET` configured outside Git
- [ ] `DATABASE_URL` points to Postgres
- [ ] SQLite rejected in production check
- [ ] `CORS_ALLOWED_ORIGINS` explicitly configured
- [ ] Redis reachable
- [ ] Nginx TLS configured
- [ ] `/health` and `/metrics` reachable
- [ ] Audit logs verified for login, admin, and execution actions
- [ ] Paper execution smoke test passes
- [ ] Live trading disabled or formally approved
- [ ] Rollback command tested in staging
- [ ] Backups configured and restore tested
