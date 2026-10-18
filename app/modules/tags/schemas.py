"""태그 입력, 검색 조건과 페이지 응답."""

from pydantic import BaseModel, ConfigDict, Field


class TagName(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=30)


class TagQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = ""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class Tag(BaseModel):
    tag_id: int
    name: str


class TagPage(BaseModel):
    items: list[Tag]
    page: int
    size: int
    total: int
    has_next: bool
