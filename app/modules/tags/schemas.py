from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TagListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str | None = None
    page: Annotated[int, Field(ge=1)] = 1
    size: Annotated[int, Field(ge=1, le=100)] = 20


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=80)]


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_id: Annotated[int, Field(gt=0, le=9223372036854775807)]
    name: Annotated[str, Field(min_length=1, max_length=80)]


class TagPage(BaseModel):
    items: list[TagRead]
    page: int
    size: int
    total: int
    has_next: bool
