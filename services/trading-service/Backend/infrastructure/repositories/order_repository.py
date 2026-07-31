from __future__ import annotations

from typing import Sequence

from sqlalchemy import select

from Backend.domain.order_models import OrderEntity


class OrderRepository:
    """Repository for persistent OMS orders."""

    def create(
        self,
        db,
        order: OrderEntity,
    ) -> OrderEntity:
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    def update(
        self,
        db,
        order: OrderEntity,
    ) -> OrderEntity:
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    def save(
        self,
        db,
        order: OrderEntity,
    ) -> OrderEntity:
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    def delete(
        self,
        db,
        order: OrderEntity,
    ) -> None:
        db.delete(order)
        db.commit()

    def get(
        self,
        db,
        order_id: int,
    ) -> OrderEntity | None:
        return db.get(OrderEntity, order_id)

    def get_by_client_order_id(
        self,
        db,
        client_order_id: str,
    ) -> OrderEntity | None:
        stmt = (
            select(OrderEntity)
            .where(OrderEntity.client_order_id == client_order_id)
        )
        return db.scalar(stmt)

    def get_by_broker_order_id(
        self,
        db,
        broker_order_id: str,
    ) -> OrderEntity | None:
        stmt = (
            select(OrderEntity)
            .where(OrderEntity.broker_order_id == broker_order_id)
        )
        return db.scalar(stmt)

    def list_open_orders(
        self,
        db,
    ) -> Sequence[OrderEntity]:

        stmt = (
            select(OrderEntity)
            .where(
                OrderEntity.status.in_(
                    [
                        "NEW",
                        "VALIDATED",
                        "SENT",
                        "OPEN",
                        "PARTIAL",
                    ]
                )
            )
            .order_by(OrderEntity.created_at)
        )

        return db.scalars(stmt).all()

    def list_completed_orders(
        self,
        db,
    ) -> Sequence[OrderEntity]:

        stmt = (
            select(OrderEntity)
            .where(
                OrderEntity.status.in_(
                    [
                        "FILLED",
                        "CANCELLED",
                        "REJECTED",
                    ]
                )
            )
            .order_by(OrderEntity.created_at.desc())
        )

        return db.scalars(stmt).all()

    def list_by_symbol(
        self,
        db,
        symbol: str,
    ) -> Sequence[OrderEntity]:

        stmt = (
            select(OrderEntity)
            .where(OrderEntity.symbol == symbol)
            .order_by(OrderEntity.created_at.desc())
        )

        return db.scalars(stmt).all()

    def list_all(
        self,
        db,
        limit: int = 100,
    ) -> Sequence[OrderEntity]:

        stmt = (
            select(OrderEntity)
            .order_by(OrderEntity.created_at.desc())
            .limit(limit)
        )

        return db.scalars(stmt).all()

    def update_status(
        self,
        db,
        order: OrderEntity,
        status: str,
    ) -> OrderEntity:

        order.status = status

        db.add(order)
        db.commit()
        db.refresh(order)

        return order

    def update_fill(
        self,
        db,
        order: OrderEntity,
        filled_qty: int,
        avg_price: float,
    ) -> OrderEntity:

        order.filled_quantity = filled_qty
        order.remaining_quantity = max(
            order.quantity - filled_qty,
            0,
        )

        order.average_price = avg_price

        if order.remaining_quantity == 0:
            order.status = "FILLED"
        else:
            order.status = "PARTIAL"

        db.add(order)
        db.commit()
        db.refresh(order)

        return order