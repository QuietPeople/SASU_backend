from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.likes import repository
from app.modules.likes.schemas import LikeState
from app.modules.users.service import require_learner
from app.modules.users.settings_service import current_epoch


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
        require_learner(session, actor_id, user_id)
        learning_epoch = current_epoch(session, user_id, record_generation)

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
