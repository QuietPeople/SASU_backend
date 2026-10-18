from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.tags import repository
from app.modules.tags.schemas import TagCreate, TagListQuery, TagPage, TagRead
from app.modules.users.service import require_admin


def list_tags(session: Session, query: TagListQuery) -> TagPage:
    try:
        with session.begin():
            items, total = repository.list_tags(session, query.q, query.page, query.size)
            return TagPage(
                items=[TagRead.model_validate(row) for row in items],
                page=query.page,
                size=query.size,
                total=total,
                has_next=query.page * query.size < total,
            )
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "태그 조회에 실패했습니다.") from exc


def create_tag(session: Session, actor_id: int, data: TagCreate) -> tuple[TagRead, bool]:
    try:
        with session.begin():
            require_admin(session, actor_id)
            repository.lock_creation(session)
            tag = repository.get_by_name(session, data.name)
            created = tag is None
            if tag is None:
                tag = repository.insert_tag(session, data.name)
            return TagRead.model_validate(tag), created
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "태그 저장에 실패했습니다.") from exc
