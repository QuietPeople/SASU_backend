from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import PositiveId


class CategoryListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=30)]


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: PositiveId
    name: Annotated[str, Field(min_length=1, max_length=80)]


class CategoryCounts(CategoryRead):
    total_count: int
    published_count: int
    draft_count: int
    private_count: int = 0


class CategoryCountsList(BaseModel):
    items: list[CategoryCounts]


class CategoryList(BaseModel):
    items: list[CategoryRead]
