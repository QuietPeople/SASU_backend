"""태그 목록 페이지와 동일 표시명 재사용 정책."""

from sqlalchemy.orm import Session

from app.modules.tags import repository
from app.modules.tags.schemas import Tag, TagPage, TagQuery


def get_tags(session: Session, query: TagQuery) -> TagPage:
    rows, total = repository.list_tags(session, query.q, (query.page - 1) * query.size, query.size)
    return TagPage(
        items=[Tag.model_validate(row) for row in rows],
        page=query.page,
        size=query.size,
        total=total,
        has_next=query.page * query.size < total,
    )


def create_tag(session: Session, name: str) -> tuple[Tag, bool]:
    try:
        repository.lock_for_write(session)
        existing = repository.find_by_name(session, name)
        created = existing is None
        row = repository.create_tag(session, name) if created else existing
        result = Tag.model_validate(row)
        session.commit()
        return result, created
    except Exception:
        session.rollback()
        raise
