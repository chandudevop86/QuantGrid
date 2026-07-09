# Strategy Registry

Strategies are governed through `Backend/domain/engine/strategy_engine.py`.

Each registered strategy has:

- `name`
- `version`
- `enabled`
- `rollout_pct`
- `supported_regimes`
- `audit_trail`

The decision pipeline consumes registry metadata directly for strategy selection. It uses `name`, `version`, `enabled`, `rollout_pct`, and `supported_regimes` without executing strategy code during selection.

Disabled strategies and strategies with `rollout_pct` set to zero are ignored by the selector.

Governance state is persisted by `Backend/application/strategy_governance_store.py` in SQLite. Set `STRATEGY_GOVERNANCE_DB_FILE` to override the default `Backend/data/strategy_governance.sqlite3` path.

`StrategyEngine` registers deterministic defaults, then hydrates persisted governance rows on startup. Version changes, enable/disable state, rollout percentage, supported regimes, owner, notes, and audit events survive process restarts.
