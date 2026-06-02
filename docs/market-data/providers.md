# QuantGrid Market Data Providers

QuantGrid supports a provider-based market data path:

`MarketDataProvider -> MarketDataService -> Redis cache -> Strategy engine -> Signal validation -> Execution`

Supported provider values:

- `yahoo`: demo and paper only.
- `kite`: Zerodha Kite Connect placeholder, fail-closed until credentials and adapter are configured.
- `upstox`: Upstox placeholder, fail-closed until credentials and adapter are configured.
- `dhan`: Dhan placeholder, fail-closed until credentials and adapter are configured.
- `fyers`: Fyers placeholder, fail-closed until credentials and adapter are configured.
- `angel`: Angel One SmartAPI placeholder, fail-closed until credentials and adapter are configured.

Configuration:

```env
QUANTGRID_MARKET_DATA_PROVIDER=yahoo
QUANTGRID_ALLOW_YAHOO_LIVE=false
QUANTGRID_MARKET_CACHE_TTL_SECONDS=5
```

Live trading remains disabled by default. If live trading is enabled, QuantGrid rejects Yahoo unless `QUANTGRID_ALLOW_YAHOO_LIVE=true` is explicitly set for a controlled test environment.

Health APIs:

- `GET /market/provider/status`
- `GET /market/feed/health`
- `GET /market/ltp/{symbol}`
- `GET /market/candles/{symbol}`

