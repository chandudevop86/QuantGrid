from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class PageRequest:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: int = Query(1, ge=1, description="1-indexed page number."),
    page_size: int = Query(
        None, ge=1, description="Number of items per page.", alias="page_size"
    ),
) -> PageRequest:
    settings = get_settings()
    size = page_size or settings.default_page_size
    size = min(size, settings.max_page_size)
    return PageRequest(page=page, page_size=size)
