# Provider adapter architecture

QuantGrid keeps **market data** and **order execution** as separate integrations.

## Market data

Strategies consume the common `MarketDataProvider` contract. Concrete providers
are selected through the market-data registry rather than from strategy code.

Currently registered provider keys include Dhan, Kite/Zerodha, Upstox, Fyers,
Angel One/SmartAPI, and Yahoo. Yahoo remains paper/demo-only unless explicitly
allowed by the existing safety configuration.

A future production NSE feed must be implemented as a licensed NSE or authorized
data-vendor adapter and then registered in the same registry. Do not scrape NSE
web pages or treat an informational/delayed interface as a trading-grade feed.

## Broker execution

Order execution uses the `BrokerClient` contract and a separate broker-adapter
registry. Dhan is currently the only concrete live execution adapter registered.
Other brokers can be added independently without changing strategies or market
data providers.

Target flow:

```text
strategy
  -> normalized market data
  -> signal
  -> risk checks
  -> selected user broker adapter
```

Market-data selection is independent:

```text
market data registry
  -> licensed NSE/vendor feed (future)
  -> broker market-data adapters
  -> Yahoo for paper/demo
  -> cache/fallback handled by the market-data service
```

## Public multi-user deployment

The current environment variables are appropriate for a single operator. A public
multi-user deployment must not store every user's broker token in one global
`.env` file. User broker credentials should be encrypted at rest, scoped per
user/account, never logged, and resolved only for that user's broker session.

Live execution remains disabled unless the existing live-trading, broker-live,
risk, and credential gates all pass.
