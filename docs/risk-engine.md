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
- `DUPLICATE_TRADE`
- `RISK_REWARD_TOO_LOW`

## Low Liquidity Rule

By default, LOW, THIN, WEAK, and ILLIQUID option liquidity block new entries. This can be set to warning-only with `RiskLimits(block_low_liquidity=False)` for controlled tests or staged rollout.

## Live Trading Position

Live trading remains disabled by default. Risk checks are necessary but not sufficient for live trading; broker configuration, HTTPS readiness, audit logging, and explicit live flags must also pass.

## Paper Trade Gate

Paper trades are allowed only when confluence is at least 70, trade quality is Good or Excellent, risk passes, discipline passes, data is fresh, and risk/reward is at least 1.5.
