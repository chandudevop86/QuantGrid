# Dhan Market Data Setup

Set the provider:

```env
QUANTGRID_MARKET_DATA_PROVIDER=dhan
QUANTGRID_BROKER_CLIENT_ID=...
QUANTGRID_BROKER_ACCESS_TOKEN=...
```

Do not commit credentials. Keep broker tokens in environment variables or your deployment secret manager.

The current Dhan market data provider is a fail-closed adapter placeholder. It validates configuration and exposes health status, but live LTP, candles, and websocket tick streaming must be connected to Dhan's market data APIs before enabling real-money execution.

