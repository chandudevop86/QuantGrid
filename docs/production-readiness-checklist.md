# Production Readiness Checklist

- [ ] `QUANTGRID_ENV=production`
- [ ] Strong `QUANTGRID_AUTH_SECRET` configured outside Git
- [ ] `DATABASE_URL` points to Postgres
- [ ] SQLite rejected in production check
- [ ] `CORS_ALLOWED_ORIGINS` explicitly configured
- [ ] `python scripts/market_data_quality_probe.py --require-execution` passes during Indian market hours for the broker/live data provider
- [ ] Backtest reports include `gross_pnl`, `total_costs`, `net_pnl`, `expectancy`, `max_drawdown`, and rejected signal counts
- [ ] Paper trading journal has at least 30 market sessions of positive net expectancy after brokerage, taxes, slippage, and rejected orders
- [ ] Infrastructure ports are bound to private interfaces or `127.0.0.1`; no Redis/Postgres/Kafka listener is publicly exposed
- [ ] Redis reachable
- [ ] Nginx TLS configured
- [ ] `/health` and `/metrics` reachable
- [ ] Audit logs verified for login, admin, and execution actions
- [ ] Paper execution smoke test passes
- [ ] Live trading disabled or formally approved
- [ ] Rollback command tested in staging
- [ ] Backups configured and restore tested
