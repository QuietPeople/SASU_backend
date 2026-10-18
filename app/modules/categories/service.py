from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.categories import repository
from app.modules.categories.schemas import CategoryCreate, CategoryList, CategoryRead
from app.modules.users.service import require_admin


def list_categories(session: Session) -> CategoryList:
    return CategoryList(
        items=[CategoryRead.model_validate(row) for row in repository.list_categories(session)]
    )


def create_category(
    session: Session, actor_id: int, data: CategoryCreate
) -> tuple[CategoryRead, bool]:
    try:
        require_admin(session, actor_id)
        repository.lock_creation(session)
        category = repository.get_by_name(session, data.name)
        created = category is None
        if category is None:
            category = repository.insert_category(session, data.name)
        result = CategoryRead.model_validate(category)
        session.commit()
        return result, created
    except Exception:
        session.rollback()
        raise


def rename_category(
    session: Session, actor_id: int, category_id: int, data: CategoryCreate
) -> CategoryRead:
    try:
        require_admin(session, actor_id)
        repository.lock_creation(session)
        category = repository.get_category(session, category_id)
        if category is None:
            raise ApiError(404, "CATEGORY_NOT_FOUND", "카테고리를 찾을 수 없습니다.")
        if category.name != data.name:
            if repository.get_by_name(session, data.name, excluding_id=category_id) is not None:
                raise ApiError(409, "CATEGORY_NAME_CONFLICT", "이미 사용 중인 카테고리 이름입니다.")
            category = repository.rename_category(session, category, data.name)
        result = CategoryRead.model_validate(category)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
