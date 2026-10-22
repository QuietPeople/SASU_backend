from uuid import UUID

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.events import repository as repo
from app.modules.events.schemas import LearningEventBody
from app.modules.users.models import UserRole
from app.modules.users.service import get_actor


def _check_epoch(learning_epoch: int, record_generation: int) -> None:
    if learning_epoch != record_generation + 1:
        raise ApiError(409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요.")


def record_event(
    session: Session,
    actor_id: int,
    event_id: UUID,
    record_generation: int,
    body: LearningEventBody,
) -> None:
    ctx = session.begin_nested() if session.in_transaction() else session.begin()
    try:
        with ctx:
            actor = get_actor(session, actor_id)
            if actor.role != UserRole.LEARNER:
                raise ApiError(403, "ROLE_NOT_ALLOWED", "학습자만 학습 이벤트를 보고할 수 있습니다.")

            learning_epoch = repo.lock_settings(session, actor.user_id)
            if learning_epoch is None:
                raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
            _check_epoch(learning_epoch, record_generation)

            if body.content_id is not None:
                status = repo.get_content_status(session, body.content_id)
                if status != "PUBLISHED":
                    raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")

            repo.insert_event(
                session,
                event_id=event_id,
                user_id=actor.user_id,
                learning_epoch=learning_epoch,
                event_type=body.event_type,
                content_id=body.content_id,
                quiz_version_id=body.quiz_version_id,
                attempt_id=body.attempt_id,
                metadata=body.metadata,
            )
    except sa_exc.IntegrityError as e:
        raise ApiError(422, "EVENT_INVALID", "이벤트 데이터가 유효하지 않습니다.") from e
