# NIFTY 1m read-only Dhan–Yahoo evidence comparison

## Purpose

The 1 October 2026 PostgreSQL ingestion audit found 334 NIFTY rows with off-minute timestamps, all flat OHLC, alongside later minute-aligned bars. An additional 14-minute block is missing on 15 October. Do not delete, round, or overwrite these historical rows.

Use `scripts/compare_nifty_providers.py` to retrieve **separately fetched Dhan INDEX/IDX_I (NIFTY index ID 13)** and **Yahoo ^NSEI** 1-minute candles. It reports timestamp alignment, full-session missing-minute counts, pairwise close differences, and the original PostgreSQL rows **without any database mutation or order placement**.

Dhan v2 reference: https://dhanhq.co/docs/v2/historical-data/ (1/5/15/25/60-minute candles; at most 90 days per request).

## Server invocation

Use the isolated PR branch or review its script before running. Do **not** merge PR #80 merely to run diagnostics.

```bash
cd /root/QuantGrid
source /root/venv/bin/activate
git fetch origin fix/smc-risk-and-causal-signals-20261016
git show origin/fix/smc-risk-and-causal-signals-20261016:scripts/compare_nifty_providers.py \
  > /tmp/compare_nifty_providers.py
PYTHONPATH=services/trading-service python /tmp/compare_nifty_providers.py \
  --start 2026-10-01 --end 2026-10-16 --include-stored \
  --output /tmp/quantgrid-nifty-provider-compare.json
```

Existing Dhan SDK credentials are loaded through QuantGrid's configured credential loader. **Never paste tokens, API keys, `.env` files, or raw authorized API responses** in GitHub issues or ChatGPT. Only share the resulting comparison JSON summary.

Dhan API: `intraday_minute_data(security_id="13", exchange_segment="IDX_I", instrument_type="INDEX", interval=1, oi=False)`. The security ID can be overridden with `--dhan-security-id`, or `DHAN_SECURITY_ID_NIFTY`. A missing SDK/token, expired token or insufficient historical-data entitlement is an execution blocker, not a validation pass.

Yahoo: direct 7-day 1m chart request through the project's YahooProvider. The default `YahooProvider.get_candles()` truncates to 500 records, so the audit reads the untruncated chart response instead. Yahoo may not cover 1 October when run on 16 October. When no overlap is available the report says `INSUFFICIENT_OVERLAP`.

## Interpretation

- `DISAGREEMENT`: at least one overlapping close exceeds the configured comparison tolerance (default 1.0 index point). Inspect `per_ist_date` and `worst_close_differences`.
- `CLOSE_PRICE_AGREEMENT`: at least 30 overlapping minutes and all close differences within tolerance. This is **only** an agreement check; examine 1m bars' open/high/low and coverage before trading research.
- `INSUFFICIENT_OVERLAP`: no defensible agreement claim is possible.
- The `provider_profiles` entries show excluded unaligned, incomplete, non-session and out-of-range observations. Compare the original `stored_postgres` record quality separately from Dhan and Yahoo.

The data are NIFTY **spot index** candles, not option premiums. They cannot establish NIFTY CE/PE strategy P&L, lots, slippage, spreads or live execution readiness. Keep the original PostgreSQL data untouched. Treat PR #80 as draft until real-data and other infrastructure checks are reviewed.
