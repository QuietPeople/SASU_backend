from sqlalchemy.orm import Session

from app.modules.tags import repository
from app.modules.tags.schemas import TagCreate, TagListQuery, TagPage, TagRead
from app.modules.users.service import require_admin


def list_tags(session: Session, query: TagListQuery) -> TagPage:
    items, total = repository.list_tags(session, query.q, query.page, query.size)
    return TagPage(
        items=[TagRead.model_validate(row) for row in items],
        page=query.page,
        size=query.size,
        total=total,
        has_next=query.page * query.size < total,
    )


def create_tag(session: Session, actor_id: int, data: TagCreate) -> tuple[TagRead, bool]:
    try:
        require_admin(session, actor_id)
        repository.lock_creation(session)
        tag = repository.get_by_name(session, data.name)
        created = tag is None
        if tag is None:
            tag = repository.insert_tag(session, data.name)
        result = TagRead.model_validate(tag)
        session.commit()
        return result, created
    except Exception:
        session.rollback()
        raise
