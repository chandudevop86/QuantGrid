"""
Application-layer ports.

Distinct from `domain/repositories.py` (persistence ports owned by the
domain), these are ports the *application* (use-case/service) layer depends
on for side effects that are not plain persistence - e.g. notifications.
Infrastructure provides the concrete adapters; services depend only on the
Protocol defined here, keeping the dependency arrow pointing inward.
"""

from app.modules.portfolio.application.interfaces.notifier import AlertNotifier

__all__ = ["AlertNotifier"]
