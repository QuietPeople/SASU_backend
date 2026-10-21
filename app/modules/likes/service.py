from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.likes import repository
from app.modules.likes.schemas import LikeState
from app.modules.users.models import UserRole
from app.modules.users.service import get_actor


def set_like(
    session: Session,
    actor_id: int,
    user_id: int,
    content_id: int,
    record_generation: int,
    *,
    liked: bool,
) -> LikeState:
    with session.begin():
        actor = get_actor(session, actor_id)
        if actor.role != UserRole.LEARNER:
            raise ApiError(403, "ROLE_NOT_ALLOWED", "학습자만 좋아요를 변경할 수 있습니다.")
        if actor.user_id != user_id:
            raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")

        # 초기화와 같은 사용자 행을 먼저 잠근다. DELETE도 세대 확인 뒤 실행한다.
        learning_epoch = repository.lock_learner_state(session, user_id)
        if learning_epoch is None:
            raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
        if learning_epoch != record_generation + 1:
            raise ApiError(
                409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요."
            )

        status = repository.lock_content_status(session, content_id)
        if status is None or (liked and status != "PUBLISHED"):
            raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")

        if liked:
            repository.insert_like(session, user_id, content_id, learning_epoch)
        else:
            repository.delete_like(session, user_id, content_id)
        result = LikeState(
            content_id=content_id,
            liked=liked,
            like_count=repository.get_like_count(session, content_id),
        )
    return result
