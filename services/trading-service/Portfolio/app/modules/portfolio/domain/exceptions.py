from __future__ import annotations


class PortfolioDomainError(Exception):
    """Base class for all Portfolio module domain errors."""

    status_code: int = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class PortfolioNotFoundError(PortfolioDomainError):
    status_code = 404

    def __init__(self, portfolio_id) -> None:
        super().__init__(f"Portfolio '{portfolio_id}' was not found.")


class HoldingNotFoundError(PortfolioDomainError):
    status_code = 404

    def __init__(self, holding_id) -> None:
        super().__init__(f"Holding '{holding_id}' was not found.")


class TransactionNotFoundError(PortfolioDomainError):
    status_code = 404

    def __init__(self, transaction_id) -> None:
        super().__init__(f"Transaction '{transaction_id}' was not found.")


class WatchlistNotFoundError(PortfolioDomainError):
    status_code = 404

    def __init__(self, watchlist_id) -> None:
        super().__init__(f"Watchlist '{watchlist_id}' was not found.")


class AlertNotFoundError(PortfolioDomainError):
    status_code = 404

    def __init__(self, alert_id) -> None:
        super().__init__(f"Alert '{alert_id}' was not found.")


class InsufficientHoldingQuantityError(PortfolioDomainError):
    status_code = 422

    def __init__(self, symbol: str, available: float, requested: float) -> None:
        super().__init__(
            f"Cannot sell {requested} units of '{symbol}'. Only {available} available."
        )


class DuplicatePortfolioNameError(PortfolioDomainError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(f"A portfolio named '{name}' already exists for this user.")


class UnauthorizedPortfolioAccessError(PortfolioDomainError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("You do not have access to this portfolio.")


class InvalidTransactionError(PortfolioDomainError):
    status_code = 422


class InsufficientDataError(PortfolioDomainError):
    status_code = 422


class InvalidDateRangeError(PortfolioDomainError):
    status_code = 422

    def __init__(self) -> None:
        super().__init__("start_date must be earlier than end_date.")
