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

Banks and NBFCs have **dedicated, separate financial scorecards**. Industrial OPM, ROCE, debt-to-equity and operating cash flow are **not** used for their eligibility or score. Insurance and financial issuers without a confirmed `financial_type` remain `UNVERIFIED`. Missing, stale, implausible or conflicting provider observations are excluded.

### Dedicated bank and NBFC screens

The provider must explicitly label `financial_type` as `BANK` or `NBFC` and identify a consistent sector. Common required fields are `roe`, `roa_pct`, `capital_adequacy_pct` (CRAR), `nim_pct`, `net_profit_growth_3y_pct`, `price_to_book`, `pledged_percentage`, market cap/price/200DMA and average daily volume. A **bank** additionally requires `gross_npa_pct`, `net_npa_pct`, `credit_growth_3y_pct`. An **NBFC** instead requires `gross_stage3_pct`, `net_stage3_pct`, `loan_book_growth_3y_pct`. All ratios are provider-observed numeric percentages except P/B and market values.

The research screen uses illustrative heuristics: market cap > ₹300 crore, ROE > 12%, ROA > 1%, earnings and loan growth > 10%, NIM > 2%, P/B < 5, pledge < 5%, impaired assets < 5%, net impairment < 3%, and CRAR ≥ 12% for banks or ≥ 15% for NBFCs, along with the liquidity and 200DMA rules. **These floors are NOT RBI regulatory capital-adequacy requirements**; actual requirements depend on the bank/NBFC class and buffers. Asset-quality ratios are not necessarily directly comparable between banks (NPA) and NBFCs (stage-three). The research score weights remain 30/25/20/15/10 but use sector-specific metrics and must not be compared blindly with industrial scores. Detailed credit-cost, provisioning, deposit mix, concentration and regulatory disclosures still require analyst review.

### SME diligence (additional mandatory data)

For **any** `market_segment: "SME"`, a stock cannot qualify unless the licensed feed also contains:

- `traded_sessions_20`: observed sessions with trades in the last 20 exchange sessions, between 0–20, requiring at least 16
- `median_bid_ask_spread_pct`: actual median observed bid/ask spread, requiring at most 2%
- `exchange_lot_size`: current venue-defined positive integer trading lot (never guessed)
- `circuit_hit_sessions_20`: actual circuit-hit sessions of the 20, at most 3
- `circuit_limit_pct`: actual positive observed circuit band of the instrument, for display and due diligence
- `promoter_holding_pct`: published promoter shareholding percentage
- `promoter_disclosure_as_of`: dated exchange/promoter disclosure, no older than 120 calendar days

A missing/invalid field or stale promoter disclosure yields `UNVERIFIED`; liquidity or circuit risk over the screening thresholds yields `REJECTED`. Even when all screens pass, SMEs show `MANUAL_REVIEW` with the actual evidence: pass is **not** a confirmation that an order of any size can safely be filled. Also independently review lot cost, float, exchange notices, price bands, settlement and promoter governance before any decision. No orders are ever submitted.

### Research-only frontend

The Investment Research page exposes four tabs: **Companies**, **Banks & NBFCs**, **SME risk review**, and **Rejected / unverified**. Each row shows the source observation dates; financials show the different accounting basis; SMEs show trades per 20 sessions, observed spreads, lot sizes, circuit history and promoter filing dates. Rejected and unverified records show why they did not qualify. The page checks the feed API every five minutes while open; the approved upstream provider is responsible for actually updating the source.

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

### Additional synthetic examples

Bank example (append to a properly dated feed in place of the industrial row):

```json
{
  "symbol": "QGBANK",
  "name": "Synthetic Bank Example",
  "sector": "Banking",
  "financial_type": "BANK",
  "market_segment": "MAINBOARD",
  "fundamentals_as_of": "2026-09-30",
  "price_as_of": "2026-10-19",
  "market_cap_cr": 25000,
  "roe": 19,
  "roa_pct": 1.8,
  "capital_adequacy_pct": 19,
  "gross_npa_pct": 2,
  "net_npa_pct": 0.7,
  "credit_growth_3y_pct": 19,
  "net_profit_growth_3y_pct": 18,
  "nim_pct": 3.6,
  "price_to_book": 2.2,
  "pledged_percentage": 0,
  "current_price": 200,
  "dma200": 160,
  "dma50": 180,
  "avg_daily_volume_1m": 50000
}
```

NBFCs change `financial_type` to `NBFC`, use a consistent NBFC sector, and supply `gross_stage3_pct`, `net_stage3_pct` and `loan_book_growth_3y_pct` in place of the bank-only NPA/credit-growth values.

For SME issuers, supplement the appropriate normal-business or financial-business row with:

```json
{
  "market_segment": "SME",
  "traded_sessions_20": 19,
  "median_bid_ask_spread_pct": 0.8,
  "exchange_lot_size": 1000,
  "circuit_hit_sessions_20": 1,
  "circuit_limit_pct": 5,
  "promoter_holding_pct": 62,
  "promoter_disclosure_as_of": "2026-09-30"
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
