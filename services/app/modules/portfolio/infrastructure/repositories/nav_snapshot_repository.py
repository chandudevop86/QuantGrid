from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portfolio.infrastructure.models import PortfolioNavSnapshotModel


class SqlAlchemyNavSnapshotRepository:
    """Repository managing daily NAV snapshots used by performance/risk engines."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self, portfolio_id: UUID, as_of_date: date, nav_value: Decimal
    ) -> PortfolioNavSnapshotModel:
        stmt = (
            pg_insert(PortfolioNavSnapshotModel)
            .values(portfolio_id=portfolio_id, as_of_date=as_of_date, nav_value=nav_value)
            .on_conflict_do_update(
                index_elements=[
                    PortfolioNavSnapshotModel.portfolio_id,
                    PortfolioNavSnapshotModel.as_of_date,
                ],
                set_={"nav_value": nav_value},
            )
            .returning(PortfolioNavSnapshotModel)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()

    async def list_for_portfolio(
        self,
        portfolio_id: UUID,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PortfolioNavSnapshotModel]:
        stmt = select(PortfolioNavSnapshotModel).where(
            PortfolioNavSnapshotModel.portfolio_id == portfolio_id
        )
        if start_date:
            stmt = stmt.where(PortfolioNavSnapshotModel.as_of_date >= start_date)
        if end_date:
            stmt = stmt.where(PortfolioNavSnapshotModel.as_of_date <= end_date)
        stmt = stmt.order_by(PortfolioNavSnapshotModel.as_of_date.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
