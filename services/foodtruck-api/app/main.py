import os
import random
import hashlib
import hmac
import json
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
import razorpay
import razorpay


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", ".env"))
load_dotenv(ENV_FILE)

DATABASE_URL = os.environ["DATABASE_URL"]

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError(
        "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be configured"
    )

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

app = FastAPI(
    title="KS Foods FoodTruck API",
    version="2.0.0",
)


# ============================================================
# DEFAULT KS FOODS MENU
# ============================================================

DEFAULT_MENU = [
    {
        "name": "Idli",
        "price": Decimal("40"),
        "food_cost": Decimal("12"),
        "image": "idli_plate_chutney_sambar.jpg",
        "category": "Tiffin",
    },
    {
        "name": "Upma",
        "price": Decimal("40"),
        "food_cost": Decimal("12"),
        "image": "suji_upma_breakfast.jpg",
        "category": "Tiffin",
    },
    {
        "name": "Vada",
        "price": Decimal("40"),
        "food_cost": Decimal("14"),
        "image": "medu_vada_sambar_chutney.jpg",
        "category": "Tiffin",
    },
    {
        "name": "Mysore Bajji",
        "price": Decimal("40"),
        "food_cost": Decimal("14"),
        "image": "mysore_bonda_bajji.jpg",
        "category": "Tiffin",
    },
    {
        "name": "Plain Dosa",
        "price": Decimal("40"),
        "food_cost": Decimal("12"),
        "image": "plain_crispy_dosa.jpg",
        "category": "Dosa",
    },
    {
        "name": "Puri",
        "price": Decimal("40"),
        "food_cost": Decimal("15"),
        "image": "puri_aloo_curry.jpg",
        "category": "Tiffin",
    },
    {
        "name": "Ghee Karam",
        "price": Decimal("60"),
        "food_cost": Decimal("20"),
        "image": "ghee_karam_dosa.jpg",
        "category": "Special Dosa",
    },
    {
        "name": "Ghee Onion",
        "price": Decimal("60"),
        "food_cost": Decimal("22"),
        "image": "ghee_onion_dosa.jpg",
        "category": "Special Dosa",
    },
    {
        "name": "Paneer Dosa",
        "price": Decimal("60"),
        "food_cost": Decimal("25"),
        "image": "paneer_masala_dosa.jpg",
        "category": "Special Dosa",
    },
    {
        "name": "Upma Pesara",
        "price": Decimal("60"),
        "food_cost": Decimal("20"),
        "image": "pesarattu_upma.jpg",
        "category": "Pesara",
    },
    {
        "name": "Onion Pesara",
        "price": Decimal("60"),
        "food_cost": Decimal("20"),
        "image": "onion_pesarattu.jpg",
        "category": "Pesara",
    },
    {
        "name": "Upma Dosa",
        "price": Decimal("50"),
        "food_cost": Decimal("18"),
        "image": "upma_filled_dosa.jpg",
        "category": "Dosa",
    },
    {
        "name": "Rava Dosa",
        "price": Decimal("50"),
        "food_cost": Decimal("17"),
        "image": "crispy_rava_dosa.jpg",
        "category": "Dosa",
    },
    {
        "name": "Onion Dosa",
        "price": Decimal("50"),
        "food_cost": Decimal("18"),
        "image": "onion_dosa_roast.jpg",
        "category": "Dosa",
    },
    {
        "name": "Masala Dosa",
        "price": Decimal("50"),
        "food_cost": Decimal("18"),
        "image": "masala_dosa.jpg",
        "category": "Dosa",
    },
    {
        "name": "Pesara",
        "price": Decimal("50"),
        "food_cost": Decimal("18"),
        "image": "pesara_dosa.jpg",
        "category": "Pesara",
    },
]


# ============================================================
# PYDANTIC MODELS
# ============================================================

class OrderItem(BaseModel):
    name: str
    quantity: int = Field(gt=0)
    price: Decimal = Field(ge=0)
    food_cost: Decimal = Field(ge=0)


class CreateOrder(BaseModel):
    payment_method: str
    items: list[OrderItem]



class PaymentItem(BaseModel):
    name: str
    quantity: int = Field(gt=0)


class CreateRazorpayOrder(BaseModel):
    items: list[PaymentItem]
    customer_name: str | None = None
    phone: str | None = None


class VerifyRazorpayPayment(BaseModel):
    order_id: int
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class CreateExpense(BaseModel):
    category: str
    description: str | None = None
    amount: Decimal = Field(gt=0)
    payment_method: str


class CreateMenuItem(BaseModel):
    name: str
    price: Decimal = Field(ge=0)
    food_cost: Decimal = Field(ge=0)
    image: str | None = None
    category: str = "Tiffin"
    available: bool = True


class UpdateMenuItem(BaseModel):
    name: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    food_cost: Decimal | None = Field(default=None, ge=0)
    image: str | None = None
    category: str | None = None
    available: bool | None = None


class AvailabilityUpdate(BaseModel):
    available: bool


class CreateStockItem(BaseModel):
    name: str
    unit: str = "kg"
    quantity: Decimal = Field(ge=0)
    minimum_quantity: Decimal = Field(default=0, ge=0)
    cost_per_unit: Decimal = Field(default=0, ge=0)
    category: str = "Raw Material"


class UpdateStockItem(BaseModel):
    quantity: Decimal | None = Field(default=None, ge=0)
    minimum_quantity: Decimal | None = Field(default=None, ge=0)
    cost_per_unit: Decimal | None = Field(default=None, ge=0)
    category: str | None = None
    unit: str | None = None


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_foodtruck_tables():
    with engine.begin() as conn:

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS menu_items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(150) NOT NULL UNIQUE,
                    price NUMERIC(12,2) NOT NULL DEFAULT 0,
                    food_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
                    image VARCHAR(255),
                    category VARCHAR(100) NOT NULL DEFAULT 'Tiffin',
                    available BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS raw_material_stock (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(150) NOT NULL UNIQUE,
                    unit VARCHAR(50) NOT NULL DEFAULT 'kg',
                    quantity NUMERIC(12,3) NOT NULL DEFAULT 0,
                    minimum_quantity NUMERIC(12,3) NOT NULL DEFAULT 0,
                    cost_per_unit NUMERIC(12,2) NOT NULL DEFAULT 0,
                    category VARCHAR(100) NOT NULL DEFAULT 'Raw Material',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        for item in DEFAULT_MENU:
            conn.execute(
                text(
                    """
                    INSERT INTO menu_items
                        (name, price, food_cost, image, category, available)
                    VALUES
                        (:name, :price, :food_cost, :image, :category, TRUE)
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
                item,
            )


@app.on_event("startup")
def startup():
    initialize_foodtruck_tables()


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "foodtruck",
        "service": "ks-foods",
    }


# ============================================================
# MENU
# ============================================================

@app.get("/menu")
def get_menu(available_only: bool = True):
    query = """
        SELECT
            id,
            name,
            price,
            food_cost,
            image,
            category,
            available,
            created_at,
            updated_at
        FROM menu_items
    """

    if available_only:
        query += " WHERE available = TRUE"

    query += " ORDER BY id ASC"

    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()

    return [dict(row) for row in rows]


@app.post("/menu")
def create_menu_item(payload: CreateMenuItem):
    with engine.begin() as conn:
        try:
            item_id = conn.execute(
                text(
                    """
                    INSERT INTO menu_items
                        (name, price, food_cost, image, category, available)
                    VALUES
                        (:name, :price, :food_cost, :image, :category, :available)
                    RETURNING id
                    """
                ),
                payload.model_dump(),
            ).scalar_one()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not create menu item: {exc}",
            ) from exc

    return {
        "id": item_id,
        **payload.model_dump(),
    }


@app.patch("/menu/{item_id}")
def update_menu_item(
    item_id: int,
    payload: UpdateMenuItem,
):
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(400, "No changes supplied")

    allowed = {
        "name",
        "price",
        "food_cost",
        "image",
        "category",
        "available",
    }

    changes = {
        key: value
        for key, value in changes.items()
        if key in allowed
    }

    assignments = []
    params = {"id": item_id}

    for key, value in changes.items():
        assignments.append(f"{key} = :{key}")
        params[key] = value

    assignments.append("updated_at = CURRENT_TIMESTAMP")

    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE menu_items
                SET {", ".join(assignments)}
                WHERE id = :id
                RETURNING
                    id,
                    name,
                    price,
                    food_cost,
                    image,
                    category,
                    available,
                    updated_at
                """
            ),
            params,
        )

        row = result.mappings().first()

    if row is None:
        raise HTTPException(404, "Menu item not found")

    return dict(row)


@app.patch("/menu/{item_id}/availability")
def update_menu_availability(
    item_id: int,
    payload: AvailabilityUpdate,
):
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE menu_items
                SET
                    available = :available,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                RETURNING
                    id,
                    name,
                    price,
                    food_cost,
                    image,
                    category,
                    available
                """
            ),
            {
                "id": item_id,
                "available": payload.available,
            },
        )

        row = result.mappings().first()

    if row is None:
        raise HTTPException(404, "Menu item not found")

    return {
        "message": (
            "Menu item is now available"
            if payload.available
            else "Menu item is now unavailable"
        ),
        "item": dict(row),
    }


@app.delete("/menu/{item_id}")
def delete_menu_item(item_id: int):
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                DELETE FROM menu_items
                WHERE id = :id
                RETURNING id, name
                """
            ),
            {"id": item_id},
        )

        row = result.mappings().first()

    if row is None:
        raise HTTPException(404, "Menu item not found")

    return {
        "deleted": True,
        **dict(row),
    }


# ============================================================
# ORDERS
# ============================================================

@app.post("/orders")
def create_order(payload: CreateOrder):
    payment = payload.payment_method.upper()

    if payment not in {"CASH", "UPI"}:
        raise HTTPException(400, "Payment must be CASH or UPI")

    if not payload.items:
        raise HTTPException(
            400,
            "Order must contain at least one item",
        )

    # Validate that submitted menu items currently exist and are available.
    with engine.connect() as conn:
        menu_rows = conn.execute(
            text(
                """
                SELECT name, price, food_cost, available
                FROM menu_items
                WHERE name = ANY(:names)
                """
            ),
            {
                "names": list({item.name for item in payload.items}),
            },
        ).mappings().all()

    menu_by_name = {
        row["name"]: row
        for row in menu_rows
    }

    for item in payload.items:
        menu_item = menu_by_name.get(item.name)

        if menu_item is None:
            raise HTTPException(
                400,
                f"Menu item not found: {item.name}",
            )

        if not menu_item["available"]:
            raise HTTPException(
                400,
                f"{item.name} is currently unavailable",
            )

    subtotal = sum(
        item.price * item.quantity
        for item in payload.items
    )

    food_cost = sum(
        item.food_cost * item.quantity
        for item in payload.items
    )

    order_number = str(random.randint(1000, 9999))

    with engine.begin() as conn:

        while conn.execute(
            text(
                "SELECT 1 FROM orders WHERE order_number = :n"
            ),
            {"n": order_number},
        ).first():

            order_number = str(random.randint(1000, 9999))

        order_id = conn.execute(
            text(
                """
                INSERT INTO orders
                    (
                        order_number,
                        payment_method,
                        status,
                        subtotal,
                        food_cost,
                        total
                    )
                VALUES
                    (
                        :number,
                        :payment,
                        'COMPLETED',
                        :subtotal,
                        :food_cost,
                        :total
                    )
                RETURNING id
                """
            ),
            {
                "number": order_number,
                "payment": payment,
                "subtotal": subtotal,
                "food_cost": food_cost,
                "total": subtotal,
            },
        ).scalar_one()

        for item in payload.items:
            line_total = item.price * item.quantity
            line_food_cost = item.food_cost * item.quantity

            conn.execute(
                text(
                    """
                    INSERT INTO order_items
                        (
                            order_id,
                            item_name,
                            quantity,
                            unit_price,
                            unit_food_cost,
                            line_total,
                            line_food_cost
                        )
                    VALUES
                        (
                            :order_id,
                            :name,
                            :quantity,
                            :price,
                            :food_cost,
                            :line_total,
                            :line_food_cost
                        )
                    """
                ),
                {
                    "order_id": order_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "food_cost": item.food_cost,
                    "line_total": line_total,
                    "line_food_cost": line_food_cost,
                },
            )

    return {
        "id": order_id,
        "order_number": order_number,
        "payment_method": payment,
        "status": "COMPLETED",
        "total": subtotal,
        "food_cost": food_cost,
        "message": f"Order {order_number} submitted successfully",
    }


@app.get("/orders")
def get_orders():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    o.id,
                    o.order_number,
                    o.payment_method,
                    o.status,
                    o.total,
                    o.food_cost,
                    o.created_at,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'name', oi.item_name,
                                'quantity', oi.quantity,
                                'price', oi.unit_price
                            )
                        ) FILTER (WHERE oi.id IS NOT NULL),
                        '[]'
                    ) AS items
                FROM orders o
                LEFT JOIN order_items oi
                    ON oi.order_id = o.id
                GROUP BY o.id
                ORDER BY o.created_at DESC
                """
            )
        ).mappings().all()

    return [dict(row) for row in rows]



# ============================================================
# RAZORPAY PAYMENTS
# ============================================================

@app.post("/payments/create-order")
def create_razorpay_order(payload: CreateRazorpayOrder):
    if not payload.items:
        raise HTTPException(
            400,
            "Order must contain at least one item",
        )

    requested_names = [item.name for item in payload.items]

    with engine.connect() as conn:
        menu_rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    name,
                    price,
                    food_cost,
                    available
                FROM menu_items
                WHERE name = ANY(:names)
                """
            ),
            {"names": list(set(requested_names))},
        ).mappings().all()

    menu_by_name = {
        row["name"]: row
        for row in menu_rows
    }

    subtotal = Decimal("0")
    food_cost = Decimal("0")
    normalized_items = []

    for item in payload.items:
        menu_item = menu_by_name.get(item.name)

        if menu_item is None:
            raise HTTPException(
                400,
                f"Menu item not found: {item.name}",
            )

        if not menu_item["available"]:
            raise HTTPException(
                400,
                f"{item.name} is currently unavailable",
            )

        unit_price = Decimal(str(menu_item["price"]))
        unit_food_cost = Decimal(str(menu_item["food_cost"]))

        line_total = unit_price * item.quantity
        line_food_cost = unit_food_cost * item.quantity

        subtotal += line_total
        food_cost += line_food_cost

        normalized_items.append(
            {
                "name": item.name,
                "quantity": item.quantity,
                "price": unit_price,
                "food_cost": unit_food_cost,
                "line_total": line_total,
                "line_food_cost": line_food_cost,
            }
        )

    if subtotal <= 0:
        raise HTTPException(
            400,
            "Order amount must be greater than zero",
        )

    amount_paise = int(
        (subtotal * Decimal("100")).quantize(Decimal("1"))
    )

    order_number = str(random.randint(1000, 9999))

    with engine.begin() as conn:

        while conn.execute(
            text(
                "SELECT 1 FROM orders WHERE order_number = :n"
            ),
            {"n": order_number},
        ).first():
            order_number = str(random.randint(1000, 9999))

        local_order_id = conn.execute(
            text(
                """
                INSERT INTO orders
                    (
                        order_number,
                        payment_method,
                        status,
                        subtotal,
                        food_cost,
                        total
                    )
                VALUES
                    (
                        :number,
                        'RAZORPAY',
                        'PAYMENT_PENDING',
                        :subtotal,
                        :food_cost,
                        :total
                    )
                RETURNING id
                """
            ),
            {
                "number": order_number,
                "subtotal": subtotal,
                "food_cost": food_cost,
                "total": subtotal,
            },
        ).scalar_one()

        for item in normalized_items:
            conn.execute(
                text(
                    """
                    INSERT INTO order_items
                        (
                            order_id,
                            item_name,
                            quantity,
                            unit_price,
                            unit_food_cost,
                            line_total,
                            line_food_cost
                        )
                    VALUES
                        (
                            :order_id,
                            :name,
                            :quantity,
                            :price,
                            :food_cost,
                            :line_total,
                            :line_food_cost
                        )
                    """
                ),
                {
                    "order_id": local_order_id,
                    **item,
                },
            )

    # Create Razorpay order only after the local order exists.
    try:
        razor_order = razorpay_client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": order_number,
                "notes": {
                    "foodtruck_order_id": str(local_order_id),
                    "foodtruck_order_number": order_number,
                },
            }
        )
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE orders
                    SET status = 'PAYMENT_FAILED'
                    WHERE id = :id
                    """
                ),
                {"id": local_order_id},
            )

        raise HTTPException(
            502,
            "Unable to create Razorpay payment order",
        ) from exc

    provider_order_id = razor_order["id"]

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO payments
                    (
                        order_id,
                        provider,
                        provider_order_id,
                        amount,
                        amount_paise,
                        currency,
                        status
                    )
                VALUES
                    (
                        :order_id,
                        'RAZORPAY',
                        :provider_order_id,
                        :amount,
                        :amount_paise,
                        'INR',
                        'CREATED'
                    )
                """
            ),
            {
                "order_id": local_order_id,
                "provider_order_id": provider_order_id,
                "amount": subtotal,
                "amount_paise": amount_paise,
            },
        )

    return {
        "order_id": local_order_id,
        "order_number": order_number,
        "razorpay_order_id": provider_order_id,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "amount": amount_paise,
        "currency": "INR",
        "total": subtotal,
    }


@app.post("/payments/verify")
def verify_razorpay_payment(payload: VerifyRazorpayPayment):
    with engine.connect() as conn:
        payment_row = conn.execute(
            text(
                """
                SELECT
                    p.id,
                    p.order_id,
                    p.provider_order_id,
                    p.provider_payment_id,
                    p.amount_paise,
                    p.status,
                    o.status AS order_status
                FROM payments p
                JOIN orders o
                    ON o.id = p.order_id
                WHERE p.order_id = :order_id
                  AND p.provider = 'RAZORPAY'
                """
            ),
            {"order_id": payload.order_id},
        ).mappings().first()

    if payment_row is None:
        raise HTTPException(
            404,
            "Razorpay payment record not found",
        )

    if payload.razorpay_order_id != payment_row["provider_order_id"]:
        raise HTTPException(
            400,
            "Razorpay order ID mismatch",
        )

    # Signature is calculated from the SERVER-STORED Razorpay order ID.
    signature_payload = (
        f"{payment_row['provider_order_id']}|"
        f"{payload.razorpay_payment_id}"
    )

    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        signature_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_signature,
        payload.razorpay_signature,
    ):
        raise HTTPException(
            400,
            "Invalid Razorpay payment signature",
        )

    # Ask Razorpay for the actual payment state.
    try:
        razor_payment = razorpay_client.payment.fetch(
            payload.razorpay_payment_id
        )
    except Exception as exc:
        raise HTTPException(
            502,
            "Unable to verify Razorpay payment status",
        ) from exc

    actual_order_id = razor_payment.get("order_id")
    actual_amount = int(razor_payment.get("amount", 0))
    actual_status = razor_payment.get("status")

    if actual_order_id != payment_row["provider_order_id"]:
        raise HTTPException(
            400,
            "Razorpay payment belongs to a different order",
        )

    if actual_amount != int(payment_row["amount_paise"]):
        raise HTTPException(
            400,
            "Razorpay payment amount mismatch",
        )

    if actual_status != "captured":
        raise HTTPException(
            400,
            f"Razorpay payment is not captured: {actual_status}",
        )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE payments
                SET
                    provider_payment_id = :payment_id,
                    status = 'CAPTURED',
                    method = :method,
                    signature_verified = TRUE,
                    webhook_event = COALESCE(
                        webhook_event,
                        'checkout.verify'
                    ),
                    updated_at = CURRENT_TIMESTAMP,
                    paid_at = COALESCE(
                        paid_at,
                        CURRENT_TIMESTAMP
                    )
                WHERE id = :payment_id_record
                """
            ),
            {
                "payment_id": payload.razorpay_payment_id,
                "method": razor_payment.get("method"),
                "payment_id_record": payment_row["id"],
            },
        )

        conn.execute(
            text(
                """
                UPDATE orders
                SET
                    status = 'COMPLETED',
                    payment_method = 'RAZORPAY'
                WHERE id = :order_id
                  AND status <> 'COMPLETED'
                """
            ),
            {"order_id": payload.order_id},
        )

    return {
        "success": True,
        "order_id": payload.order_id,
        "status": "COMPLETED",
        "payment_id": payload.razorpay_payment_id,
        "message": "Payment verified successfully",
    }


@app.post("/payments/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()

    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        raise HTTPException(
            400,
            "Missing Razorpay webhook signature",
        )

    if not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(
            500,
            "Razorpay webhook secret is not configured",
        )

    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_signature,
        signature,
    ):
        raise HTTPException(
            400,
            "Invalid Razorpay webhook signature",
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            400,
            "Invalid webhook JSON",
        ) from exc

    event = payload.get("event", "")

    payment_entity = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    order_entity = (
        payload.get("payload", {})
        .get("order", {})
        .get("entity", {})
    )

    provider_order_id = (
        payment_entity.get("order_id")
        or order_entity.get("id")
    )

    provider_payment_id = payment_entity.get("id")

    if not provider_order_id:
        return {
            "received": True,
            "processed": False,
            "reason": "No Razorpay order ID",
        }

    if event in {"payment.captured", "order.paid"}:

        with engine.begin() as conn:
            payment_row = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        order_id,
                        amount_paise,
                        status
                    FROM payments
                    WHERE provider_order_id = :provider_order_id
                      AND provider = 'RAZORPAY'
                    """
                ),
                {
                    "provider_order_id": provider_order_id,
                },
            ).mappings().first()

            if payment_row is not None:

                webhook_amount = payment_entity.get("amount")

                if (
                    webhook_amount is not None
                    and int(webhook_amount)
                    != int(payment_row["amount_paise"])
                ):
                    raise HTTPException(
                        400,
                        "Webhook payment amount mismatch",
                    )

                conn.execute(
                    text(
                        """
                        UPDATE payments
                        SET
                            provider_payment_id =
                                COALESCE(
                                    :payment_id,
                                    provider_payment_id
                                ),
                            status = 'CAPTURED',
                            method =
                                COALESCE(
                                    :method,
                                    method
                                ),
                            signature_verified = TRUE,
                            webhook_event = :event,
                            updated_at = CURRENT_TIMESTAMP,
                            paid_at = COALESCE(
                                paid_at,
                                CURRENT_TIMESTAMP
                            )
                        WHERE id = :payment_record_id
                        """
                    ),
                    {
                        "payment_id": provider_payment_id,
                        "method": payment_entity.get("method"),
                        "event": event,
                        "payment_record_id": payment_row["id"],
                    },
                )

                conn.execute(
                    text(
                        """
                        UPDATE orders
                        SET
                            status = 'COMPLETED',
                            payment_method = 'RAZORPAY'
                        WHERE id = :order_id
                          AND status <> 'COMPLETED'
                        """
                    ),
                    {
                        "order_id": payment_row["order_id"],
                    },
                )

    elif event == "payment.failed":

        with engine.begin() as conn:
            payment_row = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        order_id,
                        status
                    FROM payments
                    WHERE provider_order_id = :provider_order_id
                      AND provider = 'RAZORPAY'
                    """
                ),
                {
                    "provider_order_id": provider_order_id,
                },
            ).mappings().first()

            if payment_row is not None:

                # Never downgrade an already successful payment.
                if payment_row["status"] != "CAPTURED":
                    conn.execute(
                        text(
                            """
                            UPDATE payments
                            SET
                                provider_payment_id =
                                    COALESCE(
                                        :payment_id,
                                        provider_payment_id
                                    ),
                                status = 'FAILED',
                                method =
                                    COALESCE(
                                        :method,
                                        method
                                    ),
                                webhook_event = :event,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :payment_record_id
                            """
                        ),
                        {
                            "payment_id": provider_payment_id,
                            "method": payment_entity.get("method"),
                            "event": event,
                            "payment_record_id": payment_row["id"],
                        },
                    )

                    conn.execute(
                        text(
                            """
                            UPDATE orders
                            SET status = 'PAYMENT_FAILED'
                            WHERE id = :order_id
                              AND status <> 'COMPLETED'
                            """
                        ),
                        {
                            "order_id": payment_row["order_id"],
                        },
                    )

    return {
        "received": True,
        "processed": True,
        "event": event,
    }


# ============================================================
# RAW MATERIAL / STOCK
# ============================================================

@app.get("/stock")
def get_stock():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    name,
                    unit,
                    quantity,
                    minimum_quantity,
                    cost_per_unit,
                    category,
                    CASE
                        WHEN quantity <= minimum_quantity
                        THEN TRUE
                        ELSE FALSE
                    END AS low_stock,
                    created_at,
                    updated_at
                FROM raw_material_stock
                ORDER BY name ASC
                """
            )
        ).mappings().all()

    return [dict(row) for row in rows]


@app.post("/stock")
def create_stock_item(payload: CreateStockItem):
    with engine.begin() as conn:
        try:
            stock_id = conn.execute(
                text(
                    """
                    INSERT INTO raw_material_stock
                        (
                            name,
                            unit,
                            quantity,
                            minimum_quantity,
                            cost_per_unit,
                            category
                        )
                    VALUES
                        (
                            :name,
                            :unit,
                            :quantity,
                            :minimum_quantity,
                            :cost_per_unit,
                            :category
                        )
                    RETURNING id
                    """
                ),
                payload.model_dump(),
            ).scalar_one()

        except Exception as exc:
            raise HTTPException(
                400,
                f"Could not create stock item: {exc}",
            ) from exc

    return {
        "id": stock_id,
        **payload.model_dump(),
    }


@app.patch("/stock/{stock_id}")
def update_stock_item(
    stock_id: int,
    payload: UpdateStockItem,
):
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            400,
            "No stock changes supplied",
        )

    assignments = []

    params = {
        "id": stock_id,
    }

    for key, value in changes.items():
        assignments.append(f"{key} = :{key}")
        params[key] = value

    assignments.append(
        "updated_at = CURRENT_TIMESTAMP"
    )

    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE raw_material_stock
                SET {", ".join(assignments)}
                WHERE id = :id
                RETURNING
                    id,
                    name,
                    unit,
                    quantity,
                    minimum_quantity,
                    cost_per_unit,
                    category,
                    updated_at
                """
            ),
            params,
        )

        row = result.mappings().first()

    if row is None:
        raise HTTPException(
            404,
            "Stock item not found",
        )

    return dict(row)


# ============================================================
# EXPENSES
# ============================================================

@app.post("/expenses")
def create_expense(payload: CreateExpense):
    payment = payload.payment_method.upper()

    if payment not in {"CASH", "UPI"}:
        raise HTTPException(
            400,
            "Payment must be CASH or UPI",
        )

    with engine.begin() as conn:
        expense_id = conn.execute(
            text(
                """
                INSERT INTO expenses
                    (
                        category,
                        description,
                        amount,
                        payment_method
                    )
                VALUES
                    (
                        :category,
                        :description,
                        :amount,
                        :payment
                    )
                RETURNING id
                """
            ),
            {
                "category": payload.category,
                "description": payload.description,
                "amount": payload.amount,
                "payment": payment,
            },
        ).scalar_one()

    return {
        "id": expense_id,
        "category": payload.category,
        "amount": payload.amount,
        "payment_method": payment,
    }


@app.get("/expenses")
def get_expenses():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    category,
                    description,
                    amount,
                    payment_method,
                    created_at
                FROM expenses
                ORDER BY created_at DESC
                """
            )
        ).mappings().all()

    return [dict(row) for row in rows]


# ============================================================
# DASHBOARD
# ============================================================

@app.get("/dashboard")
def dashboard():
    with engine.connect() as conn:

        sales = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(total), 0),
                    COALESCE(SUM(food_cost), 0),
                    COUNT(*),
                    COALESCE(
                        SUM(total) FILTER (
                            WHERE payment_method = 'CASH'
                        ),
                        0
                    ),
                    COALESCE(
                        SUM(total) FILTER (
                            WHERE payment_method = 'UPI'
                        ),
                        0
                    ),
                    COALESCE(
                        SUM(total) FILTER (
                            WHERE payment_method = 'RAZORPAY'
                        ),
                        0
                    )
                FROM orders
                WHERE status = 'COMPLETED'
                """
            )
        ).one()

        expenses = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(amount), 0),
                    COALESCE(
                        SUM(amount) FILTER (
                            WHERE payment_method = 'CASH'
                        ),
                        0
                    ),
                    COALESCE(
                        SUM(amount) FILTER (
                            WHERE payment_method = 'UPI'
                        ),
                        0
                    )
                FROM expenses
                """
            )
        ).one()

        available_menu = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM menu_items
                WHERE available = TRUE
                """
            )
        ).scalar_one()

        total_menu = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM menu_items
                """
            )
        ).scalar_one()

        low_stock = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM raw_material_stock
                WHERE quantity <= minimum_quantity
                """
            )
        ).scalar_one()

    total_sales = Decimal(str(sales[0]))
    food_cost = Decimal(str(sales[1]))
    order_count = int(sales[2])

    cash_sales = Decimal(str(sales[3]))
    upi_sales = Decimal(str(sales[4]))
    razorpay_sales = Decimal(str(sales[5]))

    total_expenses = Decimal(str(expenses[0]))
    cash_expenses = Decimal(str(expenses[1]))
    upi_expenses = Decimal(str(expenses[2]))

    profit = (
        total_sales
        - food_cost
        - total_expenses
    )

    cash_balance = (
        cash_sales
        - cash_expenses
    )

    avg_order = (
        total_sales / order_count
        if order_count
        else Decimal("0")
    )

    return {
        "sales": total_sales,
        "food_cost": food_cost,
        "orders": order_count,
        "expenses": total_expenses,
        "profit": profit,
        "avg_order": avg_order,
        "cash_sales": cash_sales,
        "upi_sales": upi_sales,
        "razorpay_sales": razorpay_sales,
        "cash_expenses": cash_expenses,
        "upi_expenses": upi_expenses,
        "cash_balance": cash_balance,
        "target": Decimal("25000"),
        "menu_total": total_menu,
        "menu_available": available_menu,
        "menu_unavailable": total_menu - available_menu,
        "low_stock": int(low_stock),
    }
