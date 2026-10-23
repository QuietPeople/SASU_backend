from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.users import settings_repository as repo
from app.modules.users.models import UserRole
from app.modules.users.service import get_actor
from app.modules.users.settings_schemas import (
    FeedPosition,
    PatchSettingsBody,
    UpdateFeedPositionBody,
    UserSettings,
)


def _require_same_learner(session: Session, actor_id: int, user_id: int):
    actor = get_actor(session, actor_id)
    if actor.role != UserRole.LEARNER:
        raise ApiError(403, "ROLE_NOT_ALLOWED", "학습자만 수행할 수 있습니다.")
    if actor.user_id != user_id:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    return actor


def _require_same_user(session: Session, actor_id: int, user_id: int):
    actor = get_actor(session, actor_id)
    if actor.user_id != user_id:
        raise ApiError(404, "USER_NOT_FOUND", "대상 사용자를 찾을 수 없습니다.")
    return actor


def _check_epoch(learning_epoch: int | None, record_generation: int) -> None:
    if learning_epoch is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
    if learning_epoch != record_generation + 1:
        raise ApiError(409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요.")


def _build_settings(row) -> UserSettings:
    return UserSettings(
        onboarding_status=row["onboarding_status"],
        review_interval=row["review_interval"],
        interests=row["interests"],
        record_generation=row["learning_epoch"] - 1,
    )


def get_settings(session: Session, actor_id: int, user_id: int) -> UserSettings:
    _require_same_user(session, actor_id, user_id)
    row = repo.get_settings(session, user_id)
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
    return _build_settings(row)


def patch_settings(
    session: Session,
    actor_id: int,
    user_id: int,
    record_generation: int,
    body: PatchSettingsBody,
) -> UserSettings:
    ctx = session.begin_nested() if session.in_transaction() else session.begin()
    with ctx:
        _require_same_learner(session, actor_id, user_id)

        learning_epoch = repo.lock_settings(session, user_id)
        _check_epoch(learning_epoch, record_generation)

        if body.interest_category_ids is not None:
            missing = repo.check_missing_category_ids(session, body.interest_category_ids)
            if missing:
                raise ApiError(
                    422,
                    "VALIDATION_ERROR",
                    "존재하지 않는 카테고리가 포함되어 있습니다.",
                    [{"field": "interest_category_ids", "reason": "category_not_found"}],
                )
            repo.replace_interests(session, user_id, body.interest_category_ids)

        fields: dict[str, object] = {}
        if body.onboarding_status is not None:
            fields["onboarding_status"] = body.onboarding_status
        if body.review_interval is not None:
            fields["review_interval"] = body.review_interval
        if fields:
            repo.update_settings(session, user_id, **fields)

        row = repo.get_settings(session, user_id)

    return _build_settings(row)


def get_feed_position(session: Session, actor_id: int, user_id: int) -> FeedPosition:
    _require_same_user(session, actor_id, user_id)
    row = repo.get_feed_position(session, user_id)
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
    resume_unavailable = bool(row["resume_unavailable"])
    last_content_id = None if resume_unavailable else row["last_content_id"]
    return FeedPosition(last_content_id=last_content_id, resume_unavailable=resume_unavailable)


def update_feed_position(
    session: Session,
    actor_id: int,
    user_id: int,
    record_generation: int,
    body: UpdateFeedPositionBody,
) -> None:
    ctx = session.begin_nested() if session.in_transaction() else session.begin()
    with ctx:
        _require_same_learner(session, actor_id, user_id)

        learning_epoch = repo.lock_settings(session, user_id)
        _check_epoch(learning_epoch, record_generation)

        if body.context == "FEED":
            status = repo.lock_content_status(session, body.content_id)
            if status is None or status != "PUBLISHED":
                raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")
            repo.update_last_content(session, user_id, body.content_id)


def current_epoch(
    session: Session, user_id: int, generation: int | None = None, *, write: bool = True
) -> int:
    epoch = repo.lock_settings(session, user_id, write=write)
    if epoch is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
    if generation is not None and epoch != generation + 1:
        raise ApiError(409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요.")
    return epoch
