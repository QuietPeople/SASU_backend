from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.categories.models import Category


def list_categories(session: Session) -> list[Category]:
    return list(session.scalars(select(Category).order_by(Category.category_id)))


def lock_creation(session: Session) -> None:
    # DB에 이름 UNIQUE가 없으므로, 생성·이름 수정을 직렬화한 뒤 이름을 확인한다.
    # SQLite 단위 테스트에서는 PostgreSQL의 테이블 잠금을 사용하지 않는다.
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("LOCK TABLE sasu.categories IN SHARE ROW EXCLUSIVE MODE"))


def get_by_name(session: Session, name: str, excluding_id: int | None = None) -> Category | None:
    statement = select(Category).where(Category.name == name)
    if excluding_id is not None:
        statement = statement.where(Category.category_id != excluding_id)
    return session.scalar(statement.order_by(Category.category_id).limit(1))


def insert_category(session: Session, name: str) -> Category:
    category = Category(name=name)
    session.add(category)
    session.flush()
    return category


def get_category(session: Session, category_id: int) -> Category | None:
    return session.get(Category, category_id)


def rename_category(session: Session, category: Category, name: str) -> Category:
    category.name = name
    category.updated_at = datetime.now(UTC)
    session.flush()
    return category
