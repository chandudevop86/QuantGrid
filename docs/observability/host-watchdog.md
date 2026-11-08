# Host watchdog rollout (not automatically deployed)

The read-only systemd timer checks backend, worker, PostgreSQL, Redis, and the local
backend health endpoint every minute. It emits a small JSON status line to journald.
It does not restart services, contact Dhan, modify trading mode, or send orders.

After review, on the Ubuntu host:
```bash
sudo cp deploy/systemd/quantgrid-host-watchdog.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quantgrid-host-watchdog.timer
systemctl list-timers quantgrid-host-watchdog.timer
journalctl -u quantgrid-host-watchdog.service -n 20 --no-pager
```

For genuine 24/7 alerts, forward journald watchdog failures to CloudWatch or another
independent monitoring service and configure notifications. No alert destination is
configured by this PR. Service recovery is deliberately not automated until recovery
and trading safety behavior are reviewed. Dhan authentication and feed freshness are
not yet covered; local API reachability is not proof of broker health.
