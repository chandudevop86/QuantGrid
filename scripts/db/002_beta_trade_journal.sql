CREATE TABLE IF NOT EXISTS trade_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    signal TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'recorded',
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target REAL NOT NULL,
    exit_price REAL,
    pnl REAL NOT NULL DEFAULT 0,
    quantity INTEGER,
    reason TEXT,
    exit_reason TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trade_journal_created
ON trade_journal(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_journal_strategy
ON trade_journal(strategy);

CREATE INDEX IF NOT EXISTS idx_trade_journal_symbol
ON trade_journal(symbol);
