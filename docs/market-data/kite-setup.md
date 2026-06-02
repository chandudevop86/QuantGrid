# Zerodha Kite Market Data Setup

Set the provider:

```env
QUANTGRID_MARKET_DATA_PROVIDER=kite
KITE_API_KEY=...
KITE_ACCESS_TOKEN=...
```

Do not commit keys or access tokens. Store them only in environment variables or your deployment secret manager.

The current Kite provider is a fail-closed adapter placeholder. It validates configuration and exposes health status, but live LTP, candles, and websocket tick streaming must be connected to Kite Connect before enabling real-money execution.

