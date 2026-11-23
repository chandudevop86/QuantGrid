# Host watchdog rollout (not automatically deployed)

The read-only systemd timer checks backend, worker, PostgreSQL, Redis, and the local
backend health endpoint every minute. It emits a small JSON status line to journald.
It does not restart services, contact Dhan, modify trading mode, or send orders.

It also reads `/var/lib/quantgrid/worker-progress.json`, atomically updated by
the worker loop, each strategy and each completed automatic scan. During NSE
weekday trading hours, a missing progress record or a scan completion older than
five minutes is unhealthy. The worker's configured holiday list is included in
the progress record. Startup has a 90-second grace period. Outside the expected
session, an idle scanner is healthy. `QUANTGRID_WORKER_PROGRESS_FILE`,
`QUANTGRID_WATCHDOG_SCAN_STALE_SECONDS` and
`QUANTGRID_WATCHDOG_STARTUP_GRACE_SECONDS` override those defaults.

After review, on the Ubuntu host:
```bash
sudo cp deploy/systemd/quantgrid-host-watchdog.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quantgrid-host-watchdog.timer
systemctl list-timers quantgrid-host-watchdog.timer
journalctl -u quantgrid-host-watchdog.service -n 20 --no-pager
```

To route failure changes and recovery to your alert receiver, set
`QUANTGRID_WATCHDOG_WEBHOOK_URL` in `/etc/quantgrid/watchdog.env` (mode 0600).
The receiver must accept an HTTPS POST with the JSON watchdog report. The URL is
never written to the journal. The installer preserves an existing configuration.
No destination is preconfigured. The watchdog suppresses repeated successfully
delivered failures, sends recovery, and retries failed deliveries on subsequent
one-minute runs. Delivery state is stored in `/var/lib/quantgrid`.

The on-host watchdog requires EC2 to be running. An independent uptime monitor or
CloudWatch alarm is still needed to report total host/network loss. Dhan
authentication and provider-specific quote health are checked by the trading
execution path; local API reachability alone does not establish broker health.
