# Automatic NIFTY option paper trading

NIFTY BUY signals select a long CE, and SELL signals select a long PE. Selection
uses the nearest active expiry and the strike closest to the underlying signal
price. Contract identity and lot size come from Dhan's detailed instrument master.
Fills use the selected contract's fresh ask and whole lots. Exits use fresh bids.

The default premium stop is 20%, configurable with
`QUANTGRID_OPTION_PAPER_STOP_LOSS_PCT`. The existing scan risk budget and reward
ratio apply, with a default 2:1 reward ratio. The monitor attempts session square-off
from 15:20 IST when a fresh, liquid contract quote is available. Missing data or
insufficient depth leaves an explicit rejection or monitor error for inspection.

The existing option ledger stores orders, positions, marks, exits and audit rows.
Its default path is `services/trading-service/Backend/data/option_paper.sqlite3`,
overridable by `QUANTGRID_OPTION_PAPER_LEDGER`. Backend and worker must use the
same setting and shared persistent file. Legacy option ledgers retain their rows.
Positions API responses include these trades, using negative position IDs to
distinguish option ledger records. Manual exits and Exit All use verified bids.

Existing premium, account loss, entry-count, quantity, position and kill-switch
checks apply. Duplicate signal retries return the original stored fill. The
candidate-only setting remains available for existing users. The installer turns
that setting off for actual paper simulation. Broker data access is read-only.

After deploying the reviewed commit into `/root/QuantGrid`, run as root:

```bash
bash scripts/install_option_paper_watchdog.sh
```

The installer restarts backend and worker, enables automatic option paper
execution and the one-minute host watchdog, and prints service and journal
results. It appends a systemd environment-file override containing only paper
scan settings. It does not read or rewrite the existing credential file.

The watchdog checks backend, worker, PostgreSQL, Redis and the local API. A 200
response with degraded application health fails the check. Reports go to journald.
Timer activation proves scheduling. Worker journal results and saved option IDs
must still be inspected to verify production trade generation.

Rollback the application commit and remove
`/etc/systemd/system/quantgrid-worker.service.d/auto-option-paper.conf`, then run
`systemctl daemon-reload` and restart backend and worker. Retain the option ledger
to preserve trade history. Stop new entries before reverting while positions are
open, and close or continue monitoring those positions through the option service.
