from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas import Page, PageQuery
from app.core.types import PositiveId


class TagListQuery(PageQuery):
    model_config = ConfigDict(str_strip_whitespace=True)

    q: str | None = None


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=30)]


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_id: PositiveId
    name: Annotated[str, Field(min_length=1, max_length=80)]


class TagPage(Page[TagRead]):
    pass
