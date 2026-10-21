from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import repository as contents_repository
from app.modules.contents.models import ContentStatus
from app.modules.contents.service import build_content_summary, is_video_available
from app.modules.saved_contents import repository, temporary_bridge
from app.modules.saved_contents.repository import SavedCandidate
from app.modules.saved_contents.schemas import (
    SavedContentsPage,
    SavedContentsQuery,
    SavedItem,
    SaveState,
)
from app.modules.users.models import UserRole
from app.modules.users.repository import get_user
from app.modules.users.service import get_actor


def _lock_epoch(session: Session, user_id: int) -> int:
    epoch = temporary_bridge.lock_current_epoch(session, user_id)
    if epoch is None:
        raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    return epoch


def set_saved(
    session: Session,
    actor_id: int,
    user_id: int,
    content_id: int,
    record_generation: int,
    *,
    saved: bool,
) -> SaveState:
    with session.begin():
        actor = get_actor(session, actor_id)
        if actor.role != UserRole.LEARNER:
            raise ApiError(403, "ROLE_NOT_ALLOWED", "학습자만 저장 상태를 변경할 수 있습니다.")
        if actor.user_id != user_id:
            raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
        epoch = _lock_epoch(session, user_id)
        if epoch != record_generation + 1:
            raise ApiError(
                409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요."
            )
        content = contents_repository.get_content_for_update(session, content_id)
        if content is None or (saved and content.status != ContentStatus.PUBLISHED):
            raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")
        if saved:
            repository.insert_saved_content(session, user_id, content_id, epoch)
        else:
            repository.delete_saved_content(session, user_id, content_id)
        result = SaveState(content_id=content_id, saved=saved)
    return result


def list_saved_contents(
    session: Session,
    actor_id: int,
    user_id: int,
    query: SavedContentsQuery,
    storage: LocalVideoStorage,
) -> SavedContentsPage:
    with session.begin():
        actor = get_actor(session, actor_id)
        if actor.role == UserRole.LEARNER and actor.user_id != user_id:
            raise ApiError(404, "USER_NOT_FOUND", "조회 가능한 학습자가 없습니다.")
        target = get_user(session, user_id)
        if target is None or target.role != UserRole.LEARNER:
            raise ApiError(404, "USER_NOT_FOUND", "조회 가능한 학습자가 없습니다.")
        # 후보와 개인 상태를 읽는 사이에 초기화·저장 변경이 끼어들지 않게 같은 행을 잠근다.
        _lock_epoch(session, user_id)
        if (
            query.category_id is not None
            and contents_repository.get_category(session, query.category_id) is None
        ):
            raise ApiError(404, "CATEGORY_NOT_FOUND", "지정한 카테고리가 없습니다.")
        candidates = repository.list_saved_candidates(
            session, user_id, category_id=query.category_id
        )
        playable = filter_playable_candidates(candidates, storage)
        presentations = temporary_bridge.load_saved_presentations(
            session, [item.content for item in playable], user_id
        )
        items = [
            SavedItem(
                content=build_content_summary(presentation, actor_id), saved_at=candidate.saved_at
            )
            for candidate, presentation in zip(playable, presentations, strict=True)
        ]
        result = paginate_saved_items(items, query)
    return result


def filter_playable_candidates(
    candidates: Sequence[SavedCandidate], storage: LocalVideoStorage
) -> list[SavedCandidate]:
    """원래 저장 순서를 유지하며 파일을 이용할 수 없는 후보만 제외한다."""
    return [item for item in candidates if is_video_available(item.video, storage)]


def paginate_saved_items(
    items: Sequence[SavedItem], query: SavedContentsQuery
) -> SavedContentsPage:
    """재생 가능 여부를 필터링하고 정렬한 전체 항목에만 페이지를 적용한다."""
    total = len(items)
    start = (query.page - 1) * query.size
    end = start + query.size
    return SavedContentsPage(
        items=list(items[start:end]),
        page=query.page,
        size=query.size,
        total=total,
        has_next=end < total,
    )
