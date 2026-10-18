"""목업 행위자 역할 확인. X-Actor-Id는 로그인 인증 수단이 아니다."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.dependencies import ActorId
from app.db.session import get_db
from app.modules.users.service import check_admin_role, get_actor


@dataclass(frozen=True)
class Actor:
    user_id: int
    role: str


def require_actor(
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
) -> Actor:
    user = get_actor(session, actor_id, not_found_message="사용자를 찾을 수 없습니다.")
    return Actor(user_id=user.user_id, role=user.role)


def require_admin(actor: Annotated[Actor, Depends(require_actor)]) -> int:
    check_admin_role(actor.role, message="관리자만 이용할 수 있습니다.")
    return actor.user_id
