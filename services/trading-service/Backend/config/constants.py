"""
Backend/config/constants.py

Centralized constants for QuantGrid.
Avoid hardcoded strings throughout the project.
"""

from enum import StrEnum


# ==========================================================
# Providers
# ==========================================================

class Provider(StrEnum):
    YAHOO = "yahoo"
    DHAN = "dhan"


# ==========================================================
# Time Frames
# ==========================================================

class TimeFrame(StrEnum):
    M1 = "1m"
    M2 = "2m"
    M3 = "3m"
    M5 = "5m"
    M10 = "10m"
    M15 = "15m"
    M25 = "25m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1wk"
    MN1 = "1mo"


# ==========================================================
# Exchanges
# ==========================================================

class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    NSE_FNO = "NSE_FNO"


# ==========================================================
# Broker Products
# ==========================================================

class ProductType(StrEnum):
    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"


# ==========================================================
# Order Types
# ==========================================================

class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_MARKET = "SL-M"
    STOPLOSS = "STOPLOSS"


# ==========================================================
# Transaction Types
# ==========================================================

class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


# ==========================================================
# Trade Status
# ==========================================================

class TradeStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXITED = "EXITED"


# ==========================================================
# Position Side
# ==========================================================

class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


# ==========================================================
# Signal Types
# ==========================================================

class SignalType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


# ==========================================================
# Market Status
# ==========================================================

class MarketStatus(StrEnum):
    PREOPEN = "PREOPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


# ==========================================================
# Strategy Names
# ==========================================================

class Strategy(StrEnum):
    BREAKOUT = "breakout"
    SUPPLY_DEMAND = "supply_demand"
    RSI = "rsi"
    MTF = "mtf"
    VWAP = "vwap"
    MEAN_REVERSION = "mean_reversion"
    BTST = "btst"


# ==========================================================
# Risk Levels
# ==========================================================

class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ==========================================================
# AI Decision
# ==========================================================

class AIDecision(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SKIP = "SKIP"


# ==========================================================
# Cache Keys
# ==========================================================

class CacheKey(StrEnum):
    MARKET = "market"
    OPTION_CHAIN = "option_chain"
    PROFILE = "profile"
    POSITIONS = "positions"
    ORDERS = "orders"


# ==========================================================
# API Status
# ==========================================================

class APIStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


# ==========================================================
# Logging Levels
# ==========================================================

class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"