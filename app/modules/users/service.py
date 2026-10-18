"""업로드의 관리자 확인과 공개 사용자 식별 정보 조회."""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.users import repository
from app.modules.users.models import User as UserModel
from app.modules.users.models import UserRole
from app.modules.users.schemas import User, UserList


def get_actor(
    session: Session,
    actor_id: int,
    *,
    not_found_message: str = "행위자 사용자가 없습니다.",
) -> UserModel:
    actor = repository.get_user(session, actor_id)
    if actor is None:
        raise ApiError(404, "USER_NOT_FOUND", not_found_message)
    return actor


def check_admin_role(role: str, *, message: str = "관리자만 수행할 수 있습니다.") -> None:
    if role != UserRole.ADMIN:
        raise ApiError(403, "ROLE_NOT_ALLOWED", message)


def require_admin(session: Session, actor_id: int) -> UserModel:
    """호출 서비스의 트랜잭션 안에서 사용한다. 실제 로그인 인증은 아니다."""
    actor = get_actor(session, actor_id)
    check_admin_role(actor.role)
    return actor


def get_users(session: Session) -> UserList:
    return UserList(items=list(repository.list_users(session)))


def get_user(session: Session, user_id: int) -> User:
    user = repository.find_user(session, user_id)
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    return User.model_validate(user)
