"""Installable KS Foods delivery routes.

Import `router` from this module in the FastAPI app after the database engine is
created, then run Alembic migration 0011_foodtruck_delivery_orders.
"""
from .delivery_routes import router

__all__ = ["router"]
