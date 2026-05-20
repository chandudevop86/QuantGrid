from __future__ import annotations

import time

from fastapi import HTTPException, status


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.time()
        attempts = [item for item in self._attempts.get(key, []) if now - item < window_seconds]
        if len(attempts) >= limit:
            self._attempts[key] = attempts
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )
        attempts.append(now)
        self._attempts[key] = attempts

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)


rate_limiter = InMemoryRateLimiter()
