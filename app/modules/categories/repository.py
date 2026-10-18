"""기존 sasu.categories를 조회·수정한다. 커밋은 서비스에서 결정한다."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_categories(session: Session):
    return (
        session.execute(text("SELECT category_id, name FROM sasu.categories ORDER BY category_id"))
        .mappings()
        .all()
    )


def lock_for_write(session: Session) -> None:
    # 이름 UNIQUE가 없는 기존 스키마에서 생성·수정의 검사와 쓰기를 직렬화한다.
    # 일반 SELECT와 FK 참조 조회는 이 잠금과 함께 진행할 수 있다.
    session.execute(text("LOCK TABLE sasu.categories IN SHARE ROW EXCLUSIVE MODE"))


def find_category(session: Session, category_id: int):
    return (
        session.execute(
            text("SELECT category_id, name FROM sasu.categories WHERE category_id = :category_id"),
            {"category_id": category_id},
        )
        .mappings()
        .one_or_none()
    )


def find_by_name(session: Session, name: str, excluding_id: int | None = None):
    return (
        session.execute(
            text(
                """
            SELECT category_id, name FROM sasu.categories
            WHERE name = :name
              AND (CAST(:excluding_id AS bigint) IS NULL OR category_id <> :excluding_id)
            ORDER BY category_id LIMIT 1
            """
            ),
            {"name": name, "excluding_id": excluding_id},
        )
        .mappings()
        .one_or_none()
    )


def create_category(session: Session, name: str):
    return (
        session.execute(
            text("INSERT INTO sasu.categories (name) VALUES (:name) RETURNING category_id, name"),
            {"name": name},
        )
        .mappings()
        .one()
    )


def rename_category(session: Session, category_id: int, name: str):
    return (
        session.execute(
            text(
                """
            UPDATE sasu.categories SET name = :name, updated_at = clock_timestamp()
            WHERE category_id = :category_id RETURNING category_id, name
            """
            ),
            {"category_id": category_id, "name": name},
        )
        .mappings()
        .one()
    )
