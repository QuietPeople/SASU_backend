"""목업 행위자 역할 확인. X-Actor-Id는 로그인 인증 수단이 아니다."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.db.session import get_db

MAX_BIGINT = 2**63 - 1


@dataclass(frozen=True)
class Actor:
    user_id: int
    role: str


def require_actor(
    actor_id: Annotated[int, Header(alias="X-Actor-Id", gt=0, le=MAX_BIGINT)],
    session: Annotated[Session, Depends(get_db)],
) -> Actor:
    user = (
        session.execute(
            text("SELECT user_id, role FROM sasu.app_users WHERE user_id = :actor_id"),
            {"actor_id": actor_id},
        )
        .mappings()
        .one_or_none()
    )
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    return Actor(user_id=user["user_id"], role=user["role"])


def require_admin(actor: Annotated[Actor, Depends(require_actor)]) -> int:
    if actor.role != "ADMIN":
        raise ApiError(403, "ROLE_NOT_ALLOWED", "관리자만 이용할 수 있습니다.")
    return actor.user_id
