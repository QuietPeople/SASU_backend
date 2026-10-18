"""카테고리 중복 이름 정책과 쓰기 트랜잭션을 관리한다."""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.categories import repository
from app.modules.categories.schemas import Category, CategoryList


def get_categories(session: Session) -> CategoryList:
    return CategoryList(
        items=[Category.model_validate(row) for row in repository.list_categories(session)]
    )


def create_category(session: Session, name: str) -> tuple[Category, bool]:
    try:
        repository.lock_for_write(session)
        existing = repository.find_by_name(session, name)
        created = existing is None
        row = repository.create_category(session, name) if created else existing
        result = Category.model_validate(row)
        session.commit()
        return result, created
    except Exception:
        session.rollback()
        raise


def rename_category(session: Session, category_id: int, name: str) -> Category:
    try:
        repository.lock_for_write(session)
        current = repository.find_category(session, category_id)
        if current is None:
            raise ApiError(404, "CATEGORY_NOT_FOUND", "카테고리를 찾을 수 없습니다.")
        if current["name"] == name:
            result = Category.model_validate(current)
        else:
            if repository.find_by_name(session, name, excluding_id=category_id) is not None:
                raise ApiError(409, "CATEGORY_NAME_CONFLICT", "이미 사용 중인 카테고리 이름입니다.")
            result = Category.model_validate(repository.rename_category(session, category_id, name))
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
