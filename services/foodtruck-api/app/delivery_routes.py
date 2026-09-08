from decimal import Decimal
from typing import Literal
import os
import random

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

router = APIRouter()


class DeliveryAddress(BaseModel):
    house: str = Field(min_length=1, max_length=200)
    street: str = Field(min_length=1, max_length=200)
    area: str = Field(min_length=1, max_length=200)
    landmark: str | None = Field(default=None, max_length=200)
    instructions: str | None = Field(default=None, max_length=500)


class DeliveryOrderItem(BaseModel):
    name: str
    quantity: int = Field(gt=0)


class DeliveryCreateOrder(BaseModel):
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    payment_method: Literal["CASH", "UPI"]
    items: list[DeliveryOrderItem] = Field(min_length=1)
    order_type: Literal["LIVE", "DELIVERY"] = "LIVE"
    delivery_address: DeliveryAddress | None = None
    payment_confirmed: bool = False


class DeliveryStatusUpdate(BaseModel):
    status: str


LIVE_STATUSES = {"RECEIVED", "ACCEPTED", "PREPARING", "READY", "COMPLETED", "CANCELLED"}
DELIVERY_STATUSES = {"RECEIVED", "ACCEPTED", "PREPARING", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"}


def _main():
    from app.main import engine
    return engine


def _delivery_fee(subtotal: Decimal) -> Decimal:
    base = Decimal(os.getenv("DELIVERY_FEE", "20"))
    free_threshold = Decimal(os.getenv("FREE_DELIVERY_THRESHOLD", "300"))
    return Decimal("0") if subtotal >= free_threshold else base


def _menu(items):
    engine = _main()
    names = list({item.name for item in items})
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, price, food_cost, available FROM menu_items WHERE name = ANY(:names)"),
            {"names": names},
        ).mappings().all()
    return {row["name"]: row for row in rows}


def _number(conn):
    number = str(random.randint(1000, 9999))
    while conn.execute(text("SELECT 1 FROM orders WHERE order_number=:n"), {"n": number}).first():
        number = str(random.randint(1000, 9999))
    return number


@router.post("/orders")
def create_order_v2(payload: DeliveryCreateOrder):
    if payload.order_type == "DELIVERY" and payload.delivery_address is None:
        raise HTTPException(400, "Delivery address is required")
    if payload.payment_method == "UPI" and not payload.payment_confirmed:
        raise HTTPException(400, "Please confirm that the UPI payment was made")

    menu = _menu(payload.items)
    subtotal = Decimal("0")
    food_cost = Decimal("0")
    normalized = []
    for item in payload.items:
        row = menu.get(item.name)
        if row is None:
            raise HTTPException(400, f"Menu item not found: {item.name}")
        if not row["available"]:
            raise HTTPException(400, f"{item.name} is currently unavailable")
        price = Decimal(str(row["price"]))
        cost = Decimal(str(row["food_cost"]))
        subtotal += price * item.quantity
        food_cost += cost * item.quantity
        normalized.append((item.name, item.quantity, price, cost))

    fee = _delivery_fee(subtotal) if payload.order_type == "DELIVERY" else Decimal("0")
    total = subtotal + fee
    payment_status = "PENDING" if payload.payment_method == "CASH" else "PENDING_MANUAL"

    engine = _main()
    with engine.begin() as conn:
        number = _number(conn)
        order_id = conn.execute(
            text("""
                INSERT INTO orders
                    (order_number, payment_method, status, subtotal, food_cost, total,
                     customer_name, phone, order_type, delivery_address, delivery_fee, payment_status)
                VALUES
                    (:number, :payment, 'RECEIVED', :subtotal, :food_cost, :total,
                     :customer_name, :phone, :order_type, CAST(:address AS jsonb), :fee, :payment_status)
                RETURNING id
            """),
            {
                "number": number, "payment": payload.payment_method,
                "subtotal": subtotal, "food_cost": food_cost, "total": total,
                "customer_name": payload.customer_name.strip(), "phone": payload.phone.strip(),
                "order_type": payload.order_type,
                "address": payload.delivery_address.model_dump_json() if payload.delivery_address else None,
                "fee": fee, "payment_status": payment_status,
            },
        ).scalar_one()
        for name, quantity, price, cost in normalized:
            conn.execute(text("""
                INSERT INTO order_items
                    (order_id, item_name, quantity, unit_price, unit_food_cost, line_total, line_food_cost)
                VALUES (:order_id, :name, :quantity, :price, :cost, :line_total, :line_food_cost)
            """), {
                "order_id": order_id, "name": name, "quantity": quantity,
                "price": price, "cost": cost,
                "line_total": price * quantity,
                "line_food_cost": cost * quantity,
            })

    return {
        "id": order_id, "order_number": number, "order_type": payload.order_type,
        "payment_method": payload.payment_method, "payment_status": payment_status,
        "status": "RECEIVED", "subtotal": subtotal, "delivery_fee": fee, "total": total,
        "message": f"Order {number} received successfully",
    }


@router.get("/orders/track/{order_number}")
def track_order(order_number: str, phone: str = Query(min_length=10, max_length=20)):
    engine = _main()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, order_number, customer_name, phone, payment_method, payment_status,
                   status, order_type, subtotal, delivery_fee, total, delivery_address, created_at
            FROM orders WHERE order_number=:number AND phone=:phone
        """), {"number": order_number, "phone": phone.strip()}).mappings().first()
    if row is None:
        raise HTTPException(404, "Order not found")
    return dict(row)


@router.patch("/orders/{order_id}")
def update_order_status_v2(order_id: int, payload: DeliveryStatusUpdate):
    status = payload.status.upper()
    engine = _main()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT order_type FROM orders WHERE id=:id"), {"id": order_id}).mappings().first()
        if row is None:
            raise HTTPException(404, "Order not found")
        allowed = DELIVERY_STATUSES if row["order_type"] == "DELIVERY" else LIVE_STATUSES
        if status not in allowed:
            raise HTTPException(400, f"Invalid status for {row['order_type']} order")
        updated = conn.execute(text("""
            UPDATE orders SET status=:status WHERE id=:id
            RETURNING id, order_number, status, order_type, payment_method, payment_status, total
        """), {"id": order_id, "status": status}).mappings().one()
    return dict(updated)


@router.get("/delivery/config")
def delivery_config():
    return {
        "delivery_fee": float(Decimal(os.getenv("DELIVERY_FEE", "20"))),
        "free_delivery_threshold": float(Decimal(os.getenv("FREE_DELIVERY_THRESHOLD", "300"))),
    }
