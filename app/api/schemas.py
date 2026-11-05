"""공통 페이지와 학습자·편집자 조회 조건."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class ViewQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: Literal["learner", "editor"] = "learner"


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int
    has_next: bool


def page_offset(page: int, size: int) -> int:
    """Keep out-of-range pages empty without overflowing PostgreSQL bigint."""
    return min((page - 1) * size, 2**63 - 1 - size)
