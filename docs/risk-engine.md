# Risk Engine Operator Guide

The risk engine is allowed to block any recommendation before a paper or live order is accepted.

## Validation Checks

The central risk engine checks:

- Kill switch
- Max trades per day
- Max daily loss
- Max weekly loss
- Max consecutive losses
- Max capital per trade
- Max open positions
- Stop loss exists
- Target exists
- Minimum risk/reward
- Stale market data
- High volatility
- Low option liquidity
- Slippage estimate above limit
- Bid/ask spread above limit
- Gap risk above limit
- High-impact news risk
- Holiday or thin-session risk
- Portfolio exposure above limit
- Symbol exposure above limit
- Correlated position count above limit
- Expiry-day option decay block, when enabled
- Gamma risk above limit
- Broker disconnected status
- Active broker circuit breaker
- Duplicate trade
- Expiry-day warning

## Result Contract

Every validation returns:

- `allowed`: true or false
- `reasons`: trader-readable reasons
- `risk_score`: 0 to 100
- `blocked_by`: machine-readable blocker codes
- `warnings`: non-blocking warnings

## Key Blocker Codes

- `KILL_SWITCH`
- `MAX_TRADES_PER_DAY`
- `MAX_DAILY_LOSS`
- `WEEKLY_LOSS_LIMIT`
- `MAX_CONSECUTIVE_LOSSES`
- `MAX_CAPITAL_PER_TRADE`
- `MAX_OPEN_POSITIONS`
- `STOP_LOSS_REQUIRED`
- `TARGET_REQUIRED`
- `STALE_MARKET_DATA`
- `HIGH_VOLATILITY`
- `LOW_LIQUIDITY`
- `SLIPPAGE_TOO_HIGH`
- `SPREAD_TOO_WIDE`
- `GAP_RISK`
- `NEWS_RISK`
- `HOLIDAY_RISK`
- `PORTFOLIO_EXPOSURE_LIMIT`
- `SYMBOL_EXPOSURE_LIMIT`
- `CORRELATION_LIMIT`
- `EXPIRY_DECAY_RISK`
- `GAMMA_RISK`
- `BROKER_DISCONNECTED`
- `BROKER_CIRCUIT_ACTIVE`
- `DUPLICATE_TRADE`
- `RISK_REWARD_TOO_LOW`

## Low Liquidity Rule

By default, LOW, THIN, WEAK, and ILLIQUID option liquidity block new entries. This can be set to warning-only with `RiskLimits(block_low_liquidity=False)` for controlled tests or staged rollout.

## Options Execution Hazards

Risk 2.0 blocks fresh entries when explicit context or signal metadata shows unsafe execution assumptions: excessive slippage, wide spread, large gap, excessive gamma, or broker disconnect. Expiry-day option-buying can be promoted from warning to blocker with `RiskLimits(block_expiry_day_option_buying=True)`.

High-impact news and holiday/thin-session flags block by default. Use explicit signal metadata such as `high_impact_news`, `news_impact=HIGH`, `holiday_effect`, or `market_session=HOLIDAY` so the backend, not the UI, remains the source of truth.

## Exposure And Correlation Limits

Risk 2.0 blocks concentration when signal metadata or risk context reports excessive portfolio exposure, symbol exposure, or correlated positions. Supported metadata keys are `portfolio_exposure_pct`, `total_exposure_pct`, `symbol_exposure_pct`, `instrument_exposure_pct`, `correlated_positions`, and `correlation_group_count`.

Default limits are 60% total portfolio exposure, 30% per-symbol exposure, and 2 correlated positions. Near-limit exposure remains allowed but emits warnings so operators can reduce size before hard rejection.

## Discipline Stops

Every order is checked against daily loss, weekly loss, trade count, and consecutive-loss limits before paper or live execution. Weekly P&L is calculated from closed paper trades in the last 7 days plus open unrealized P&L.

Configure weekly loss with `QUANTGRID_MAX_WEEKLY_LOSS`. If omitted, QuantGrid defaults to three times the configured daily loss. Configure the losing-streak stop with `QUANTGRID_MAX_CONSECUTIVE_LOSSES`.

## Broker Risk

Live order risk checks fail closed when the broker circuit breaker is active and return `BROKER_CIRCUIT_ACTIVE`. Paper orders remain available during broker instability so operators can continue analysis and dry-run validation without touching the broker.

## Live Trading Position

Live trading remains disabled by default. Risk checks are necessary but not sufficient for live trading; broker configuration, HTTPS readiness, audit logging, and explicit live flags must also pass.

## Paper Trade Gate

Paper trades are allowed only when confluence is at least 70, trade quality is Good or Excellent, risk passes, discipline passes, data is fresh, and risk/reward is at least 1.5.
