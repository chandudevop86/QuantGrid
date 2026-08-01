from __future__ import annotations

import enum


class Currency(str, enum.Enum):
    USD = "USD"
    INR = "INR"
    EUR = "EUR"
    GBP = "GBP"


class PortfolioType(str, enum.Enum):
    EQUITY = "EQUITY"
    MUTUAL_FUND = "MUTUAL_FUND"
    RETIREMENT = "RETIREMENT"
    MIXED = "MIXED"


class TransactionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    BONUS = "BONUS"
    SPLIT = "SPLIT"


class AssetClass(str, enum.Enum):
    EQUITY = "EQUITY"
    DEBT = "DEBT"
    CASH = "CASH"
    COMMODITY = "COMMODITY"
    REAL_ESTATE = "REAL_ESTATE"
    CRYPTO = "CRYPTO"
    OTHER = "OTHER"


class MarketCapSegment(str, enum.Enum):
    LARGE_CAP = "LARGE_CAP"
    MID_CAP = "MID_CAP"
    SMALL_CAP = "SMALL_CAP"
    MICRO_CAP = "MICRO_CAP"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReturnPeriod(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    ABSOLUTE = "ABSOLUTE"
    XIRR = "XIRR"


class AlertType(str, enum.Enum):
    TARGET_PRICE = "TARGET_PRICE"
    STOP_LOSS = "STOP_LOSS"


class AlertDirection(str, enum.Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"


class AlertStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    CANCELLED = "CANCELLED"
