from Backend.domain.trading_store_models import TradeJournalRecord


def test_trade_journal_record_matches_store_contract():
    table = TradeJournalRecord.__table__

    assert table.name == "trade_journal"
    assert set(table.columns.keys()) == {
        "id",
        "strategy",
        "signal",
        "symbol",
        "status",
        "entry",
        "stop_loss",
        "target",
        "exit_price",
        "pnl",
        "quantity",
        "reason",
        "exit_reason",
        "source",
        "created_at",
        "closed_at",
    }
    assert table.c.id.primary_key is True
    assert table.c.strategy.nullable is False
    assert table.c.signal.nullable is False
    assert table.c.symbol.nullable is False
    assert table.c.status.nullable is False
    assert table.c.entry.nullable is False
    assert table.c.stop_loss.nullable is False
    assert table.c.target.nullable is False
    assert table.c.pnl.nullable is False
    assert table.c.source.nullable is False
    assert table.c.created_at.nullable is False
