# Yahoo vs Live Providers

Yahoo Finance is useful for demos, paper testing, and development. It is not trading-grade for real-time NSE execution because feed latency, availability, symbol semantics, and exchange timestamp guarantees are not suitable for real-money order decisions.

Live execution should use a broker or NSE-grade provider such as Kite, Upstox, Dhan, Fyers, or Angel One SmartAPI.

Safety rules:

- Yahoo is paper/demo only by default.
- Live execution fails startup when provider is Yahoo.
- Live orders are blocked when ticks or candles are stale.
- Cached data may support strategy analysis only while fresh.
- Execution fails closed when the live provider is unavailable.

