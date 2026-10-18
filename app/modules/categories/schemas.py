"""카테고리 입력·출력 계약. 이름 정규화는 양끝 공백 제거만 적용한다."""

from pydantic import BaseModel, ConfigDict, Field


class CategoryName(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=30)


class Category(BaseModel):
    category_id: int
    name: str


class CategoryList(BaseModel):
    items: list[Category]
