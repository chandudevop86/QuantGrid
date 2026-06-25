from __future__ import annotations

from Backend.core.database import Base
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    job_json: Mapped[str] = mapped_column(Text, nullable=False)


class MarketPriceTickRecord(Base):
    __tablename__ = "market_price_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    exchange_timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    stored_at: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class MarketCandleRecord(Base):
    __tablename__ = "market_candles"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    interval: Mapped[str] = mapped_column(String(20), primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(40), primary_key=True)
    market_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    exchange_timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stored_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class PaperTradeRecord(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    trailing_stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_stop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    broker_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    raw_safe_broker_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    regime: Mapped[str | None] = mapped_column(String(80), nullable=True)
    signal_time: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class TradeJournalRecord(Base):
    __tablename__ = "trade_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="recorded", index=True)
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class OrderRecord(Base):
    __tablename__ = "orders"

    local_order_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_stop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="paper")
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class PositionRecord(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_stop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    open_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    closed_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    opened_at: Mapped[str] = mapped_column(String(40), nullable=False)
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class RiskStateRecord(Base):
    __tablename__ = "risk_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deactivated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    activated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deactivated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
