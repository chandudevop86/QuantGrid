# On-call Runbook

## First Checks

```bash
curl -fsS "$BASE_URL/health"
curl -fsS "$BASE_URL/metrics"
sudo systemctl status quantgrid-backend --no-pager
sudo journalctl -u quantgrid-backend -n 200 --no-pager
```

## Common Incidents

- Login failures: check auth secret consistency and database connectivity.
- Market data unavailable: check provider errors and stored cache status.
- Paper execution rejected: inspect signal shape, candle validation, risk gate, and execution constraints.
- Websocket not updating: check Redis and `/ws` proxy configuration.

## Escalation

Escalate immediately for:

- Any live trading safety issue.
- Auth bypass or suspected token compromise.
- Production database corruption.
- Repeated 5xx responses after rollback.
