# QuantGrid Market Data Providers

QuantGrid keeps market data separate from broker execution so a public deployment can support multiple brokers without coupling strategies to one vendor.

`MarketDataProvider -> MarketDataService -> Redis cache -> Strategy engine -> Signal validation -> Execution`

## Provider values

- `auto`: paper/analysis failover chain. It is deliberately rejected for live execution.
- `dhan`: Dhan market-data adapter.
- `kite` / `zerodha`: Zerodha Kite Connect boundary; currently fail-closed until the live adapter is completed.
- `upstox`: Upstox boundary; currently fail-closed until the live adapter is completed.
- `fyers`: FYERS boundary; currently fail-closed until the live adapter is completed.
- `angel` / `angelone` / `smartapi`: Angel One boundary; currently fail-closed until the live adapter is completed.
- `nse` / `nse-licensed`: reserved for an approved/licensed NSE or authorized-vendor feed. QuantGrid must not implement this by scraping NSE web pages.
- `yahoo`: demo and paper only.

## Paper failover

For development, analysis, and paper trading:

```env
QUANTGRID_MARKET_DATA_PROVIDER=auto
QUANTGRID_MARKET_DATA_PROVIDER_CHAIN=dhan,yahoo
QUANTGRID_ALLOW_YAHOO_LIVE=false
QUANTGRID_MARKET_CACHE_TTL_SECONDS=5
```

Providers are tried from left to right. If Dhan authentication expires, the paper workflow can continue with Yahoo instead of silently using very old stored candles.

The `auto` provider is never live-suitable, even if its first child is a broker feed. Live execution must select one explicit trading-grade provider. This prevents a demo source from silently becoming an execution feed.

## Licensed NSE feed

The repository contains a fail-closed `nse` provider boundary for future integration. A production implementation should connect an NSE Data & Analytics licensed feed or an authorized data vendor behind the normal `MarketDataProvider` interface.

Example future configuration:

```env
QUANTGRID_MARKET_DATA_PROVIDER=nse
NSE_DATA_LICENSE_ID=
```

The current placeholder does not fetch data and fails closed until an approved adapter is implemented.

## Broker expansion

Market data and order execution are separate concerns. Dhan, Zerodha, Upstox, FYERS, and Angel One should each have their own adapters behind stable QuantGrid interfaces. Strategies should only consume normalized symbols, LTP, candles, and validated market metadata; they should not contain broker-specific SDK calls.

For a future public/multi-user QuantGrid deployment, broker credentials must be stored per user in a protected credential store. Do not put many users' broker tokens into process-wide environment variables, application logs, frontend storage, or source control.

## Safety rules

Live trading remains disabled by default. Yahoo and automatic failover are paper/demo only. A future licensed NSE adapter or broker adapter must still pass freshness, timezone, missing-candle, risk, and execution validation before live trading can be enabled.

Health APIs:

- `GET /market/provider/status`
- `GET /market/feed/health`
- `GET /market/ltp/{symbol}`
- `GET /market/candles/{symbol}`
