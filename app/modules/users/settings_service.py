from sqlalchemy.orm import Session

from app.core.config import get_settings as get_app_settings
from app.core.exceptions import ApiError
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import repository as contents_repository
from app.modules.contents.models import VideoAsset
from app.modules.contents.service import is_video_available
from app.modules.users import settings_repository as repo
from app.modules.users.models import User, UserRole
from app.modules.users.service import get_actor, require_learner
from app.modules.users.settings_schemas import (
    FeedPosition,
    PatchSettingsBody,
    UpdateFeedPositionBody,
    UserSettings,
)


def require_state_reader(session: Session, actor_id: int, user_id: int) -> None:
    actor = get_actor(session, actor_id)
    if actor.role != UserRole.ADMIN and actor.user_id != user_id:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    target = session.get(User, user_id)
    if target is None or target.role != UserRole.LEARNER:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")


def current_epoch(
    session: Session, user_id: int, generation: int | None = None, *, write: bool = True
) -> int:
    epoch = repo.lock_settings(session, user_id, write=write)
    if epoch is None:
        raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
    if generation is not None and epoch != generation + 1:
        raise ApiError(409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요.")
    return epoch


def _build_settings(user_id: int, row) -> UserSettings:
    return UserSettings(
        user_id=user_id,
        interest_category_ids=[item["category_id"] for item in row["interests"]],
        interest_guide_completed=row["onboarding_status"] != "PENDING",
        review_interval=row["review_interval"],
        record_generation=row["learning_epoch"] - 1,
    )


def get_settings(session: Session, actor_id: int, user_id: int) -> UserSettings:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_state_reader(session, actor_id, user_id)
        current_epoch(session, user_id)
        return _build_settings(user_id, repo.get_settings(session, user_id))


def patch_settings(
    session: Session,
    actor_id: int,
    user_id: int,
    body: PatchSettingsBody,
) -> UserSettings:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_learner(session, actor_id, user_id)
        current_epoch(session, user_id)
        previous = repo.get_settings(session, user_id)
        if body.interest_guide_completed is False and previous["onboarding_status"] != "PENDING":
            raise ApiError(422, "VALIDATION_ERROR", "완료한 관심 안내를 되돌릴 수 없습니다.")
        if body.interest_category_ids is not None:
            if repo.check_missing_category_ids(session, body.interest_category_ids):
                raise ApiError(404, "CATEGORY_NOT_FOUND", "지정한 카테고리가 없습니다.")
            repo.replace_interests(session, user_id, body.interest_category_ids)
        fields = {}
        if body.review_interval is not None:
            fields["review_interval"] = body.review_interval
        if body.interest_category_ids is not None or body.interest_guide_completed is True:
            fields["onboarding_status"] = "DONE"
        repo.update_settings(session, user_id, **fields)
        return _build_settings(user_id, repo.get_settings(session, user_id))


def _feed_position(session: Session, user_id: int, epoch: int) -> FeedPosition:
    row = repo.get_feed_position(session, user_id)
    content_id = row["last_content_id"]
    available = False
    if content_id is not None:
        content = contents_repository.get_content(session, content_id)
        if content is not None and content.status == "PUBLISHED" and content.video_asset_id:
            video = session.get(VideoAsset, content.video_asset_id)
            available = is_video_available(
                video, LocalVideoStorage(get_app_settings().video_storage_root)
            )
    return FeedPosition(
        user_id=user_id,
        last_content_id=content_id,
        resume_available=available,
        record_generation=epoch - 1,
    )


def get_feed_position(session: Session, actor_id: int, user_id: int) -> FeedPosition:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_state_reader(session, actor_id, user_id)
        epoch = current_epoch(session, user_id)
        return _feed_position(session, user_id, epoch)


def update_feed_position(
    session: Session,
    actor_id: int,
    user_id: int,
    record_generation: int,
    body: UpdateFeedPositionBody,
) -> FeedPosition:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_learner(session, actor_id, user_id)
        epoch = current_epoch(session, user_id, record_generation)
        if repo.lock_content_status(session, body.last_content_id) != "PUBLISHED":
            raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")
        repo.update_last_content(session, user_id, body.last_content_id)
        return _feed_position(session, user_id, epoch)
