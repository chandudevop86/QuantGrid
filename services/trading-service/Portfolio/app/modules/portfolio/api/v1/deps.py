from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as redis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.application.interfaces.notifier import AlertNotifier
from app.modules.portfolio.application.services.alert_service import AlertService
from app.modules.portfolio.application.services.analytics_service import AnalyticsService
from app.modules.portfolio.application.services.holding_service import HoldingService
from app.modules.portfolio.application.services.performance_service import PerformanceService
from app.modules.portfolio.application.services.portfolio_service import PortfolioService
from app.modules.portfolio.application.services.rebalancing_service import RebalancingService
from app.modules.portfolio.application.services.risk_service import RiskService
from app.modules.portfolio.application.services.transaction_service import TransactionService
from app.modules.portfolio.application.services.watchlist_service import WatchlistService
from app.modules.portfolio.infrastructure.database import get_db_session, get_redis_client
from app.modules.portfolio.infrastructure.market_data import RedisMarketDataProvider
from app.modules.portfolio.infrastructure.notifier import RedisAlertNotifier
from app.modules.portfolio.infrastructure.repositories.alert_repository import SqlAlchemyAlertRepository
from app.modules.portfolio.infrastructure.repositories.holding_repository import SqlAlchemyHoldingRepository
from app.modules.portfolio.infrastructure.repositories.nav_snapshot_repository import (
    SqlAlchemyNavSnapshotRepository,
)
from app.modules.portfolio.infrastructure.repositories.portfolio_repository import (
    SqlAlchemyPortfolioRepository,
)
from app.modules.portfolio.infrastructure.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
)
from app.modules.portfolio.infrastructure.repositories.watchlist_repository import (
    SqlAlchemyWatchlistRepository,
)

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
CurrentUserDep = CurrentUser  # re-exported for readable route signatures
get_current_user_dep = get_current_user


# --------------------------------------------------------------------------- #
# Session / cache
# --------------------------------------------------------------------------- #
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    async for client in get_redis_client():
        yield client


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
def get_portfolio_repository(session: AsyncSession = Depends(get_session)) -> SqlAlchemyPortfolioRepository:
    return SqlAlchemyPortfolioRepository(session)


def get_holding_repository(session: AsyncSession = Depends(get_session)) -> SqlAlchemyHoldingRepository:
    return SqlAlchemyHoldingRepository(session)


def get_transaction_repository(session: AsyncSession = Depends(get_session)) -> SqlAlchemyTransactionRepository:
    return SqlAlchemyTransactionRepository(session)


def get_watchlist_repository(session: AsyncSession = Depends(get_session)) -> SqlAlchemyWatchlistRepository:
    return SqlAlchemyWatchlistRepository(session)


def get_alert_repository(session: AsyncSession = Depends(get_session)) -> SqlAlchemyAlertRepository:
    return SqlAlchemyAlertRepository(session)


def get_nav_snapshot_repository(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyNavSnapshotRepository:
    return SqlAlchemyNavSnapshotRepository(session)


# --------------------------------------------------------------------------- #
# External adapters
# --------------------------------------------------------------------------- #
def get_market_data_provider(client: redis.Redis = Depends(get_redis)) -> RedisMarketDataProvider:
    return RedisMarketDataProvider(client)


def get_alert_notifier(client: redis.Redis = Depends(get_redis)) -> AlertNotifier:
    return RedisAlertNotifier(client)


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #
def get_portfolio_service(
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    holding_repo: SqlAlchemyHoldingRepository = Depends(get_holding_repository),
    market_data: RedisMarketDataProvider = Depends(get_market_data_provider),
) -> PortfolioService:
    return PortfolioService(portfolio_repo, holding_repo, market_data)


def get_holding_service(
    holding_repo: SqlAlchemyHoldingRepository = Depends(get_holding_repository),
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    market_data: RedisMarketDataProvider = Depends(get_market_data_provider),
) -> HoldingService:
    return HoldingService(holding_repo, portfolio_repo, market_data)


def get_transaction_service(
    transaction_repo: SqlAlchemyTransactionRepository = Depends(get_transaction_repository),
    holding_repo: SqlAlchemyHoldingRepository = Depends(get_holding_repository),
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> TransactionService:
    return TransactionService(transaction_repo, holding_repo, portfolio_repo)


def get_performance_service(
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    transaction_repo: SqlAlchemyTransactionRepository = Depends(get_transaction_repository),
    holding_repo: SqlAlchemyHoldingRepository = Depends(get_holding_repository),
    nav_repo: SqlAlchemyNavSnapshotRepository = Depends(get_nav_snapshot_repository),
    market_data: RedisMarketDataProvider = Depends(get_market_data_provider),
) -> PerformanceService:
    return PerformanceService(portfolio_repo, transaction_repo, holding_repo, nav_repo, market_data)


def get_risk_service(
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    nav_repo: SqlAlchemyNavSnapshotRepository = Depends(get_nav_snapshot_repository),
    market_data: RedisMarketDataProvider = Depends(get_market_data_provider),
) -> RiskService:
    return RiskService(portfolio_repo, nav_repo, market_data)


def get_analytics_service(
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    holding_repo: SqlAlchemyHoldingRepository = Depends(get_holding_repository),
    nav_repo: SqlAlchemyNavSnapshotRepository = Depends(get_nav_snapshot_repository),
    market_data: RedisMarketDataProvider = Depends(get_market_data_provider),
) -> AnalyticsService:
    return AnalyticsService(portfolio_repo, holding_repo, nav_repo, market_data)


def get_watchlist_service(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
) -> WatchlistService:
    return WatchlistService(watchlist_repo)


def get_alert_service(
    alert_repo: SqlAlchemyAlertRepository = Depends(get_alert_repository),
    notifier: AlertNotifier = Depends(get_alert_notifier),
) -> AlertService:
    return AlertService(alert_repo, notifier)


def get_rebalancing_service(
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    holding_repo: SqlAlchemyHoldingRepository = Depends(get_holding_repository),
    market_data: RedisMarketDataProvider = Depends(get_market_data_provider),
) -> RebalancingService:
    return RebalancingService(portfolio_repo, holding_repo, market_data)
