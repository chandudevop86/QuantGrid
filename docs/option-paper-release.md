# Option paper integration release

This change consolidates automatic CE/PE execution, the local HTTPS health fix,
and the remaining option paper integrations. All execution remains paper-only.
Contract lot size and the fresh contract premium determine quantity and premium
capital; the NIFTY index value is not used as the option entry price.

## Acceptance and accounting

- Generic risk checks, dashboard, positions and journal include the option ledger
  once, with paper/live views isolated. Option execution keeps its atomic ledger
  limit checks. Journal editing cannot rewrite option execution records.
- Option Buyer previews and submits verified contracts with an idempotency key.
  Requested lots are either affordable in full or rejected.
- Closed option positions expose gross P&L, estimated transaction costs and net
  P&L using the existing paper cost model. These are estimates, not broker bills.
- Failed exits retain exposure and a durable recovery reason. Still-tradable
  overdue positions retry in a later session. Expired positions require an
  admin/ops review in Paper Trades: final underlying price, evidence reference,
  and explicit confirmation. This computes intrinsic value, records the actor,
  and permits a worthless option to settle at zero without fabricating a quote.
- PostgreSQL backups include a consistent SQLite option snapshot and checksum.
  See option-ledger-backups.md for restore preflight and storage limitations.
- The watchdog checks worker/scan progress during trading hours and outstanding
  option recovery even outside market hours. Optional HTTPS webhooks deduplicate
  failures and notify recovery. See observability/host-watchdog.md.

## Approved EC2 rollout

After human review and approval, fetch this PR's branch on the existing host and
fast-forward the checkout. Back up both stores before restarting services.
Run `bash scripts/install_option_paper_watchdog.sh`, then
`bash deploy/scripts/frontend.sh deploy` to publish the new UI. Preserve existing
production environment settings and risk limits. Configure any alert destination
directly in `/etc/quantgrid/watchdog.env`; do not paste its secret URL into chats.

Verify `/health` locally with `X-Forwarded-Proto: https`, the watchdog timer and
latest service report. During the next open session, check fresh contract quotes,
saved option order IDs, positions, risk totals and the journal. Automated tests
do not prove a real market-session order has been persisted on EC2.

Rollback code to the previous deployed commit and rebuild the frontend; do not
remove the ledger or restore an old database over newly recorded positions.
The added SQLite tables/columns preserve existing data. Keep entry generation
paused until exposure and storage are reconciled if rollback is necessary.
