from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.tags.models import Tag


def list_tags(session: Session, q: str | None, page: int, size: int) -> tuple[list[Tag], int]:
    query = select(Tag)
    if q:
        query = query.where(Tag.name.icontains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    offset = (page - 1) * size
    if offset >= total:
        return [], total
    items = list(session.scalars(query.order_by(Tag.tag_id).offset(offset).limit(size)))
    return items, total


def lock_creation(session: Session) -> None:
    # UNIQUE 추가 없이 서로 다른 관리자의 동시 조회·등록도 직렬화한다.
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("LOCK TABLE sasu.tags IN SHARE ROW EXCLUSIVE MODE"))


def get_by_name(session: Session, name: str) -> Tag | None:
    return session.scalar(select(Tag).where(Tag.name == name).order_by(Tag.tag_id).limit(1))


def insert_tag(session: Session, name: str) -> Tag:
    tag = Tag(name=name)
    session.add(tag)
    session.flush()
    return tag
