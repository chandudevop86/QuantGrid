from typing import Any
from fastapi import Request
from sqlalchemy.orm import Session
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.models import User
from Backend.infrastructure.broker.broker_client import (
    BrokerClient,
    broker_client_for_mode,
)
from Backend.infrastructure.broker.dhan_status import check_dhan_profile
from typing import Final



def get_broker_client(execution_mode: str) -> BrokerClient:
    return broker_client_for_mode(execution_mode)
def _broker_session_valid(settings: Any) -> bool:
    """
    Validate broker connectivity for live trading.
    """

    provider = str(getattr(settings, "broker_provider", "")).strip().lower()

    if not provider:
        return False

    if provider == str(Provider.DHAN).lower() or provider == "dhan":
        try:
            profile = check_dhan_profile(timeout=3.0)
            return bool(profile.get("connected", False))
        except Exception:
            return False

    return bool(getattr(settings, "broker_configured", False))


MAX_ENTRY_PRICE_DEVIATION: Final[float] = 0.02  # 2%