"""설정·내부 계정 정보가 포함되지 않는 사용자 식별 정보."""

from typing import Literal

from pydantic import BaseModel


class User(BaseModel):
    user_id: int
    name: str
    role: Literal["LEARNER", "ADMIN"]


class UserList(BaseModel):
    items: list[User]
