from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.users.models import User, UserRole
from app.modules.users.repository import get_user


def require_admin(session: Session, actor_id: int) -> User:
    """호출 서비스의 트랜잭션 안에서 사용한다. 실제 로그인 인증은 아니다."""
    actor = get_user(session, actor_id)
    if actor is None:
        raise ApiError(404, "USER_NOT_FOUND", "행위자 사용자가 없습니다.")
    if actor.role != UserRole.ADMIN:
        raise ApiError(403, "ROLE_NOT_ALLOWED", "관리자만 수행할 수 있습니다.")
    return actor
