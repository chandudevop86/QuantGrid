from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portfolio.domain.enums import AlertStatus
from app.modules.portfolio.domain.repositories import AlertRepository
from app.modules.portfolio.infrastructure.models import AlertModel


class SqlAlchemyAlertRepository(AlertRepository):
    """SQLAlchemy 2.0 (async) implementation of the Alert persistence port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> AlertModel:
        entity = AlertModel(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, alert_id: UUID) -> AlertModel | None:
        return await self._session.get(AlertModel, alert_id)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        offset: int,
        limit: int,
        status: str | None = None,
        alert_type: str | None = None,
    ) -> list[AlertModel]:
        stmt = select(AlertModel).where(AlertModel.user_id == user_id)
        if status:
            stmt = stmt.where(AlertModel.status == status)
        if alert_type:
            stmt = stmt.where(AlertModel.alert_type == alert_type)
        stmt = stmt.order_by(AlertModel.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID, **filters) -> int:
        stmt = select(func.count(AlertModel.id)).where(AlertModel.user_id == user_id)
        if filters.get("status"):
            stmt = stmt.where(AlertModel.status == filters["status"])
        if filters.get("alert_type"):
            stmt = stmt.where(AlertModel.alert_type == filters["alert_type"])
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_active(self) -> list[AlertModel]:
        stmt = select(AlertModel).where(AlertModel.status == AlertStatus.ACTIVE)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_symbol(self, symbol: str) -> list[AlertModel]:
        stmt = select(AlertModel).where(
            AlertModel.status == AlertStatus.ACTIVE, AlertModel.symbol == symbol.upper()
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, alert: AlertModel, **kwargs) -> AlertModel:
        for key, value in kwargs.items():
            if value is not None:
                setattr(alert, key, value)
        await self._session.flush()
        await self._session.refresh(alert)
        return alert

    async def delete(self, alert: AlertModel) -> None:
        await self._session.delete(alert)
        await self._session.flush()
