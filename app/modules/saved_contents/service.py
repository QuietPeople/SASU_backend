from sqlalchemy.orm import Session

from app.api.schemas import page_offset
from app.core.exceptions import ApiError
from app.modules.contents import repository as contents_repository
from app.modules.contents.models import ContentStatus
from app.modules.contents.service import build_content_summary
from app.modules.saved_contents import repository
from app.modules.saved_contents.schemas import (
    SavedContentsPage,
    SavedContentsQuery,
    SavedItem,
    SaveState,
)
from app.modules.users.models import UserRole
from app.modules.users.repository import get_user
from app.modules.users.service import get_actor, require_learner
from app.modules.users.settings_service import current_epoch


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
        require_learner(session, actor_id, user_id)
        epoch = current_epoch(session, user_id, record_generation)
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
) -> SavedContentsPage:
    with session.begin():
        actor = get_actor(session, actor_id)
        if actor.role == UserRole.LEARNER and actor.user_id != user_id:
            raise ApiError(404, "USER_NOT_FOUND", "조회 가능한 학습자가 없습니다.")
        target = get_user(session, user_id)
        if target is None or target.role != UserRole.LEARNER:
            raise ApiError(404, "USER_NOT_FOUND", "조회 가능한 학습자가 없습니다.")
        # 후보와 개인 상태를 읽는 사이에 초기화·저장 변경이 끼어들지 않게 같은 행을 잠근다.
        current_epoch(session, user_id)
        if (
            query.category_id is not None
            and contents_repository.get_category(session, query.category_id) is None
        ):
            raise ApiError(404, "CATEGORY_NOT_FOUND", "지정한 카테고리가 없습니다.")
        rows, total = repository.list_saved_contents(session, user_id, query)
        start = page_offset(query.page, query.size)
        presentations = contents_repository.load_presentations(
            session, [item.content for item in rows], user_id
        )
        items = [
            SavedItem(content=build_content_summary(presentation, actor_id), saved_at=row.saved_at)
            for row, presentation in zip(rows, presentations, strict=True)
        ]
        result = SavedContentsPage(
            items=items,
            page=query.page,
            size=query.size,
            total=total,
            has_next=start + query.size < total,
        )
    return result
