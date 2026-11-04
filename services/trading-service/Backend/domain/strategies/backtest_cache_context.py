"""Internal authorization for prepared backtest indicator frames."""

from contextlib import contextmanager
from contextvars import ContextVar

_CACHE_ALLOWED = ContextVar(
    "quantgrid_backtest_cache_allowed",
    default=False,
)


@contextmanager
def allow_backtest_cache():
    token = _CACHE_ALLOWED.set(True)
    try:
        yield
    finally:
        _CACHE_ALLOWED.reset(token)


def backtest_cache_allowed() -> bool:
    return _CACHE_ALLOWED.get()
