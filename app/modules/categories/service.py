from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.categories import repository
from app.modules.categories.schemas import CategoryCreate, CategoryList, CategoryRead
from app.modules.users.service import require_admin


def list_categories(session: Session) -> CategoryList:
    try:
        with session.begin():
            return CategoryList(
                items=[
                    CategoryRead.model_validate(row) for row in repository.list_categories(session)
                ]
            )
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "카테고리 조회에 실패했습니다.") from exc


def create_category(
    session: Session, actor_id: int, data: CategoryCreate
) -> tuple[CategoryRead, bool]:
    try:
        with session.begin():
            require_admin(session, actor_id)
            repository.lock_creation(session)
            category = repository.get_by_name(session, data.name)
            created = category is None
            if category is None:
                category = repository.insert_category(session, data.name)
            return CategoryRead.model_validate(category), created
    except SQLAlchemyError as exc:
        raise ApiError(500, "INTERNAL_ERROR", "카테고리 저장에 실패했습니다.") from exc
