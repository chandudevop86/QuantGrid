# Provider architecture

QuantGrid keeps market data, strategies, risk checks, and broker execution separate so the
application can support multiple brokers without coupling strategy code to one vendor.

## Market data

Implemented market-data adapters are registered centrally. Current adapters include Dhan,
Yahoo, Zerodha/Kite, Upstox, Fyers, and Angel One/SmartAPI.

Paper mode may use a failover chain. Configure Yahoo as a fallback when the primary
provider is unavailable:

```env
QUANTGRID_MARKET_DATA_PROVIDER=dhan
QUANTGRID_MARKET_DATA_FALLBACKS=yahoo
```

Multiple fallbacks may be configured as a comma-separated list. The failover wrapper is
intentionally never live-suitable. If live trading is enabled, QuantGrid selects only the
configured primary provider and retains the existing live-market-data safety checks.

Yahoo remains demo/paper-only and must not be treated as trading-grade data.

## Broker execution

Broker execution uses a separate registry. Dhan is the only live order adapter currently
implemented. Zerodha, Upstox, Fyers, and Angel One are registered as planned integrations so
future adapters can be added behind the same broker interface without changing strategies.

A registered name does not mean live execution is available. Selecting a planned broker
fails closed until its concrete order adapter is implemented and reviewed.

## NSE data

The architecture reserves NSE/authorized-vendor data as a future production market-data
source. A public or commercial deployment must use data according to the applicable NSE or
vendor licence and entitlements; website scraping is not a production data provider.

## Safety boundary

Strategies consume normalized market data and produce signals. Risk checks run before the
broker layer. Provider failover never enables live trading, changes risk limits, or submits
orders. Live execution still requires the existing explicit live-trading and broker-live
feature flags plus configured credentials.


## Health and failover visibility

The market provider health response distinguishes the configured provider from the provider
that actually served the latest paper-mode probe:

- `configured_provider`: provider selected by configuration.
- `active_provider`: provider that actually served the latest successful probe.
- `fallback_chain`: ordered provider chain considered in paper mode.
- `failover_used`: whether a fallback provider is currently active.
- `provider_mode`: `primary` or `failover`.
- `degraded`: true for provider errors, stale data, or active fallback operation.
- `execution_eligible`: true only when the active provider is live-suitable, fresh, error-free,
  and not operating through paper failover.
- `status_reason`: concise machine-readable reason such as `healthy`,
  `paper_failover_active`, `stale_market_data`, or `provider_error`.

A fresh paper fallback may therefore report `fresh=true` while also reporting
`degraded=true` and `execution_eligible=false`. This is intentional: data can remain
useful for analysis without being approved for live execution.
