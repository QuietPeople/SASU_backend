"""공통 카테고리 목록과 관리자용 추가·이름 수정 API."""

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.core.security import require_admin
from app.modules.categories import service
from app.modules.categories.schemas import Category, CategoryList, CategoryName

router = APIRouter(
    prefix="/categories",
    tags=["카테고리"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)
write_errors = {
    400: {"model": ErrorResponse, "description": "JSON 구문 오류"},
    403: {"model": ErrorResponse, "description": "관리자 역할 필요"},
    404: {"model": ErrorResponse, "description": "사용자 또는 카테고리 없음"},
}


@router.get("", response_model=CategoryList, summary="API-CAT-01 카테고리 목록 조회")
def get_categories(session: Database) -> CategoryList:
    return service.get_categories(session)


@router.post(
    "",
    status_code=201,
    response_model=Category,
    dependencies=[Depends(require_admin)],
    summary="API-CAT-02 카테고리 추가",
    responses={**write_errors, 200: {"model": Category, "description": "동일 이름 재사용"}},
)
def create_category(request: CategoryName, response: Response, session: Database) -> Category:
    category, created = service.create_category(session, request.name)
    response.status_code = 201 if created else 200
    return category


@router.patch(
    "/{category_id}",
    response_model=Category,
    dependencies=[Depends(require_admin)],
    summary="API-CAT-03 카테고리 이름 수정",
    responses={
        **write_errors,
        409: {"model": ErrorResponse, "description": "다른 카테고리의 이름과 중복"},
    },
)
def rename_category(category_id: ResourceId, request: CategoryName, session: Database) -> Category:
    return service.rename_category(session, category_id, request.name)
