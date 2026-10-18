"""기존 sasu.tags의 태그 이름 검색·생성. 이름 UNIQUE는 추가하지 않는다."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_tags(session: Session, query: str, offset: int, size: int):
    # strpos로 %·_·역슬래시를 와일드카드가 아닌 입력 문자 그대로 검색한다.
    total = session.scalar(
        text("SELECT count(*) FROM sasu.tags WHERE strpos(lower(name), lower(:q)) > 0"),
        {"q": query},
    )
    if offset >= total:
        return [], total
    rows = (
        session.execute(
            text(
                """
            SELECT tag_id, name FROM sasu.tags
            WHERE strpos(lower(name), lower(:q)) > 0
            ORDER BY tag_id LIMIT :size OFFSET :offset
            """
            ),
            {"q": query, "size": size, "offset": offset},
        )
        .mappings()
        .all()
    )
    return rows, total


def lock_for_write(session: Session) -> None:
    session.execute(text("LOCK TABLE sasu.tags IN SHARE ROW EXCLUSIVE MODE"))


def find_by_name(session: Session, name: str):
    return (
        session.execute(
            text("SELECT tag_id, name FROM sasu.tags WHERE name = :name ORDER BY tag_id LIMIT 1"),
            {"name": name},
        )
        .mappings()
        .one_or_none()
    )


def create_tag(session: Session, name: str):
    return (
        session.execute(
            text("INSERT INTO sasu.tags (name) VALUES (:name) RETURNING tag_id, name"),
            {"name": name},
        )
        .mappings()
        .one()
    )
