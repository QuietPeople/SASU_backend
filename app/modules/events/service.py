import logging

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.events import repository as repo
from app.modules.events.schemas import DISPLAY_EVENTS, LearningEvent, LearningEventBody
from app.modules.users.service import require_learner
from app.modules.users.settings_service import current_epoch

logger = logging.getLogger(__name__)

_DB_EVENTS = {
    "VIDEO_QUIZ_SHOWN": "QUIZ_DISPLAYED",
    "FEED_REVIEW_SHOWN": "QUIZ_DISPLAYED",
    "FLASHCARD_VIEWED": "CARD_OPENED",
    "FLASHCARD_FLIPPED": "CARD_REVEALED",
    "PLAY_ERROR": "PLAYBACK_ERROR",
    "SEARCH_EMPTY": "SEARCH_EMPTY",
}
_CONTEXTS = {"VIDEO_QUIZ_SHOWN": "VIDEO_END", "FEED_REVIEW_SHOWN": "FEED_REVIEW"}


def _conflict() -> ApiError:
    return ApiError(409, "EVENT_ID_CONFLICT", "다른 이벤트에 사용한 client_event_id입니다.")


def _result(row, event_type, recorded):
    return LearningEvent(
        event_id=row["event_id"],
        client_event_id=row["event_id"],
        event_type=event_type,
        occurred_at=row["occurred_at"],
        recorded=recorded,
    )


def record_event(
    session: Session,
    actor_id: int,
    user_id: int,
    record_generation: int,
    body: LearningEventBody,
) -> LearningEvent:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_learner(session, actor_id, user_id)
        epoch = current_epoch(session, user_id, record_generation)
        repo.lock_event_id(session, body.client_event_id)
        existing = repo.find_event(session, body.client_event_id)
        db_type = _DB_EVENTS[body.event_type]
        if existing and (
            existing["user_id"] != user_id
            or existing["learning_epoch"] != epoch
            or existing["event_type"] != db_type
            or existing["attempt_id"] != body.attempt_id
        ):
            raise _conflict()

        content_id, version_id = body.content_id, body.question_version_id
        if body.event_type in DISPLAY_EVENTS:
            attempt = repo.get_attempt(session, body.attempt_id)
            if (
                attempt is None
                or attempt["user_id"] != user_id
                or attempt["learning_epoch"] != epoch
            ):
                raise ApiError(404, "ATTEMPT_NOT_FOUND", "본인의 현재 풀이를 찾을 수 없습니다.")
            if (
                attempt["context"] != _CONTEXTS[body.event_type]
                or content_id is not None
                and content_id != attempt["content_id"]
                or version_id is not None
                and version_id != attempt["quiz_version_id"]
            ):
                if existing:
                    raise _conflict()
                raise ApiError(
                    422, "INVALID_EVENT_RELATION", "풀이와 이벤트의 대상·경로가 다릅니다."
                )
            content_id, version_id = attempt["content_id"], attempt["quiz_version_id"]

        if existing:
            if existing["content_id"] != content_id or existing["quiz_version_id"] != version_id:
                raise _conflict()
            return _result(existing, body.event_type, False)

        if version_id is not None:
            version_content = repo.get_version_content(session, version_id)
            if version_content is None:
                raise ApiError(404, "QUESTION_VERSION_NOT_FOUND", "문항 버전을 찾을 수 없습니다.")
            if version_content != content_id:
                raise ApiError(422, "INVALID_EVENT_RELATION", "콘텐츠와 문항 버전이 다릅니다.")
        if content_id is not None and repo.get_content_status(session, content_id) != "PUBLISHED":
            raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")
        if body.event_type in DISPLAY_EVENTS:
            displayed = repo.find_display(session, body.attempt_id)
            if displayed:
                repo.remember_retry_id(session, displayed["event_id"], body.client_event_id)
                return _result(displayed, body.event_type, False)

        row = repo.insert_event(
            session,
            event_id=body.client_event_id,
            user_id=user_id,
            epoch=epoch,
            event_type=db_type,
            content_id=content_id,
            version_id=version_id,
            attempt_id=body.attempt_id,
        )
        if body.error_code:
            logger.info("영상 재생 오류 content_id=%s code=%r", content_id, body.error_code)
        return _result(row, body.event_type, True)
