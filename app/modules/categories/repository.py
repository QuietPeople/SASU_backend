from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.categories.models import Category


def list_categories(session: Session) -> list[Category]:
    return list(session.scalars(select(Category).order_by(Category.category_id)))


def lock_creation(session: Session) -> None:
    # DB에 이름 UNIQUE가 없으므로, 쓰기를 직렬화한 뒤 기존 이름을 확인한다.
    # SQLite 단위 테스트에서는 PostgreSQL의 테이블 잠금을 사용하지 않는다.
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("LOCK TABLE sasu.categories IN SHARE ROW EXCLUSIVE MODE"))


def get_by_name(session: Session, name: str) -> Category | None:
    return session.scalar(
        select(Category).where(Category.name == name).order_by(Category.category_id).limit(1)
    )


def insert_category(session: Session, name: str) -> Category:
    category = Category(name=name)
    session.add(category)
    session.flush()
    return category
