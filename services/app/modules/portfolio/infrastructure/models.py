from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.modules.portfolio.domain.enums import (
    AlertDirection,
    AlertStatus,
    AlertType,
    AssetClass,
    Currency,
    MarketCapSegment,
    PortfolioType,
    TransactionType,
)


class Base(DeclarativeBase):
    """
    Local declarative base for the Portfolio module.

    NOTE: if the host application already defines a shared `Base` (e.g. in
    `app.core.database`), swap this import for that shared base instead of
    declaring a second metadata registry. Kept local here so this module is
    fully self-contained and does not require editing existing project files.
    """
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class PortfolioModel(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_portfolio_user_name"),
        Index("ix_portfolios_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_type: Mapped[PortfolioType] = mapped_column(
        String(30), default=PortfolioType.EQUITY, nullable=False
    )
    base_currency: Mapped[Currency] = mapped_column(String(3), default=Currency.USD, nullable=False)
    benchmark_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, default="^GSPC")
    is_archived: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    holdings: Mapped[list["HoldingModel"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["TransactionModel"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    nav_snapshots: Mapped[list["PortfolioNavSnapshotModel"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class HoldingModel(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", name="uq_holding_portfolio_symbol"),
        Index("ix_holdings_portfolio_id", "portfolio_id"),
        CheckConstraint("quantity >= 0", name="ck_holding_quantity_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_class: Mapped[AssetClass] = mapped_column(String(30), default=AssetClass.EQUITY, nullable=False)
    market_cap_segment: Mapped[MarketCapSegment] = mapped_column(
        String(30), default=MarketCapSegment.NOT_APPLICABLE, nullable=False
    )
    beta: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    portfolio: Mapped["PortfolioModel"] = relationship(back_populates="holdings")


class TransactionModel(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_portfolio_id", "portfolio_id"),
        Index("ix_transactions_portfolio_symbol", "portfolio_id", "symbol"),
        Index("ix_transactions_date", "transaction_date"),
        CheckConstraint("quantity >= 0", name="ck_transaction_quantity_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    split_ratio_from: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    split_ratio_to: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    portfolio: Mapped["PortfolioModel"] = relationship(back_populates="transactions")


class PortfolioNavSnapshotModel(Base):
    """Daily NAV (net asset value) snapshot, used as the time-series basis for
    return / risk-metric calculations (avoids recomputing from full transaction
    history on every request)."""

    __tablename__ = "portfolio_nav_snapshots"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "as_of_date", name="uq_nav_portfolio_date"),
        Index("ix_nav_portfolio_date", "portfolio_id", "as_of_date"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    nav_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    portfolio: Mapped["PortfolioModel"] = relationship(back_populates="nav_snapshots")


class WatchlistModel(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
        Index("ix_watchlists_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["WatchlistItemModel"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
        Index("ix_watchlist_items_watchlist_id", "watchlist_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    watchlist: Mapped["WatchlistModel"] = relationship(back_populates="items")


class AlertModel(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_user_id", "user_id"),
        Index("ix_alerts_symbol_status", "symbol", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(String(20), nullable=False)
    direction: Mapped[AlertDirection] = mapped_column(String(10), nullable=False)
    threshold_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(String(20), default=AlertStatus.ACTIVE, nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
