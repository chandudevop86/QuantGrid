# QuantGrid Quality Growth V2 (Research Only)

An opt-in stock discovery screen that **never** auto-buys or supplies trade signals. It is **separate** from existing sample-stock investing research and from automated paper/live execution. Outputs are for manual research only.

## Screening thresholds

Applies to non-financial, verified NSE/BSE mainboard and SME records. Requires:
- Market cap above ₹300 crore (no upper cap).
- ROE > 15%, ROCE > 18%, debt/equity < 0.5.
- Three-year revenue and profit growth > 12%, OPM > 12%.
- Promoter pledge < 5%, **positive reported operating cash flow** (₹ crore).
- P/E between 0 and 60.
- Current stock price **above** 200 DMA; monthly-average *daily* traded value exceeds ₹30 lakh.
- Observed price date no older than **7 calendar days**, financial statement date no older than **180 calendar days**, overall feed date no older than **7 calendar days**. Future-dated records rejected.

Banks, NBFCs, insurance and other financial firms require separate accounting-specific criteria; missing/invalid fields are `UNVERIFIED` and excluded. SME stocks always require manual trade-frequency/lot-size/spread/circuit evaluation regardless of their score.

Ranking weights total 100 points: quality 30, growth 25, valuation 20, momentum 15, leverage/pledge risk 10. The scoring formula is a first-cut research heuristic, **not** a backtested return model, forecast, execution approval, or investment recommendation. Without 50 DMA the momentum contribution is reduced and the gap disclosed.

## Feed integration and automatic refresh

Screener.in does **not** provide a sanctioned universal live API for this integration. **Do not scrape Screener.in, automate its login, bypass rate limits, or treat a one-time CSV upload as a live continuously updated data subscription.** Instead configure **one** authorized provider of dated financials + market data, using either a file an approved upstream updater rewrites atomically, or an explicitly allowlisted HTTPS JSON endpoint.

### Option A: licensed provider writes a local JSON file

```dotenv
QUANTGRID_QUALITY_GROWTH_FEED_PATH=/var/lib/quantgrid/quality-growth/feed.json
QUANTGRID_QUALITY_GROWTH_REFRESH_SECONDS=900
```

Create the directory with access restricted to the API operator and arrange for your approved licensed ingest job to refresh the file. The file is **not** written by QuantGrid. Do not commit actual licensed data or credentials. A nightly updater is fine; source dates are validated independently. Do not use the repository's code or secret directories as feed files.

### Option B: explicitly approved HTTPS feed

```dotenv
QUANTGRID_QUALITY_GROWTH_FEED_URL=https://licensed-provider.example.com/quantgrid/quality-growth.json
QUANTGRID_QUALITY_GROWTH_ALLOWED_HOST=licensed-provider.example.com
QUANTGRID_QUALITY_GROWTH_REFRESH_SECONDS=900
```

Optional token supplied *only* through your secret manager/API environment variable `QUANTGRID_QUALITY_GROWTH_FEED_TOKEN` (never a Git commit or dashboard field). HTTPS port 443 only, host must be explicitly configured, no redirects, 8-second timeout, maximum 2 MB body, negative response caching. Operations must verify the provider's data license, endpoint contract and reliability first.

### Expected JSON format

Below is a **synthetic schema example**, not real prices or licensed stock data. Numeric returns/margins/pledges are in percent; volume is average daily shares over approximately one month; price is rupees; cash flow/market cap in ₹ crore.

```json
{
  "source": "licensed-provider-identifier",
  "as_of": "2026-10-19",
  "stocks": [{
    "symbol": "QGTEST",
    "name": "Synthetic Schema Example Ltd",
    "sector": "Industrials",
    "market_segment": "MAINBOARD",
    "fundamentals_as_of": "2026-09-30",
    "price_as_of": "2026-10-19",
    "market_cap_cr": 4500,
    "roe": 24,
    "roce": 31,
    "debt_to_equity": 0.15,
    "sales_growth_3y": 22,
    "profit_growth_3y": 21,
    "opm": 21,
    "pledged_percentage": 0,
    "cash_from_operations_cr": 30,
    "pe": 24,
    "current_price": 200,
    "dma200": 150,
    "dma50": 175,
    "avg_daily_volume_1m": 35000
  }]
}
```

**Never load synthetic examples in production**. The optional `dma50` is a verified observation, never generated. Real source fields may need a licensed-provider-specific adapter mapping to the exact schema. Venue/segment mapping must be verified, especially SME securities. Duplicate symbol records are rejected; use a qualified venue-specific unique symbol for dual-listed listings.

### API and UI

- Authenticated read-only endpoint: `GET /investing/stocks/quality-growth`.
- Investment Research page displays V2 rankings, source date, financial date and price date, explicit missing-data warnings and SME flags.
- Frontend polls every five minutes **while open**; API refreshes the configured source after a bounded default 15-minute TTL. API does not launch a background ingestion scheduler when nobody is requesting data. The licensed provider must keep its own source updated; this feature does not subscribe to a data plan or create a real-time data feed.
- No feed means `UNCONFIGURED` with zero candidates; outages, invalid data and stale source mean `UNAVAILABLE`, **never** sample/generated substitutes.
- `execution_enabled=false` in the result is permanent. No trading worker, broker order adapter or risk limits are changed.

## Validation before deploy

```bash
PYTHONPATH=services/trading-service:services/tests /root/venv/bin/python -m pytest -q services/tests/test_quality_growth_screener.py
cd apps/frontend && npm ci && npm run build
```

Run repository CI, Security and CodeQL, obtain independent review and approved deployment. Until a real authorized feed is configured, the live screen deliberately shows **UNCONFIGURED**. Do not directly force a server update if the production checkout has dirty tracked runtime state or newer trading PRs need staged acceptance.
