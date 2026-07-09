# Risk Engine Operator Guide

The risk engine is allowed to block any recommendation before a paper or live order is accepted.

## Validation Checks

The central risk engine checks:

- Kill switch
- Max trades per day
- Max daily loss
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
- Expiry-day option decay block, when enabled
- Gamma risk above limit
- Broker disconnected status
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
- `EXPIRY_DECAY_RISK`
- `GAMMA_RISK`
- `BROKER_DISCONNECTED`
- `DUPLICATE_TRADE`
- `RISK_REWARD_TOO_LOW`

## Low Liquidity Rule

By default, LOW, THIN, WEAK, and ILLIQUID option liquidity block new entries. This can be set to warning-only with `RiskLimits(block_low_liquidity=False)` for controlled tests or staged rollout.

## Options Execution Hazards

Risk 2.0 blocks fresh entries when explicit context or signal metadata shows unsafe execution assumptions: excessive slippage, wide spread, large gap, excessive gamma, or broker disconnect. Expiry-day option-buying can be promoted from warning to blocker with `RiskLimits(block_expiry_day_option_buying=True)`.

High-impact news and holiday/thin-session flags block by default. Use explicit signal metadata such as `high_impact_news`, `news_impact=HIGH`, `holiday_effect`, or `market_session=HOLIDAY` so the backend, not the UI, remains the source of truth.

## Live Trading Position

Live trading remains disabled by default. Risk checks are necessary but not sufficient for live trading; broker configuration, HTTPS readiness, audit logging, and explicit live flags must also pass.

## Paper Trade Gate

Paper trades are allowed only when confluence is at least 70, trade quality is Good or Excellent, risk passes, discipline passes, data is fresh, and risk/reward is at least 1.5.
