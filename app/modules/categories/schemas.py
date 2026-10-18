from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CategoryListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=30)]


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: Annotated[int, Field(gt=0, le=9223372036854775807)]
    name: Annotated[str, Field(min_length=1, max_length=80)]


class CategoryList(BaseModel):
    items: list[CategoryRead]
