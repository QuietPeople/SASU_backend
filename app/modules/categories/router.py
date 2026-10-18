from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import ActorId, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.db.session import get_db
from app.modules.categories import service
from app.modules.categories.schemas import (
    CategoryCreate,
    CategoryList,
    CategoryListQuery,
    CategoryRead,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "",
    response_model=CategoryList,
    operation_id="API-CAT-01",
    summary="카테고리 목록 조회",
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def list_categories(
    query: Annotated[CategoryListQuery, Query()], session: Annotated[Session, Depends(get_db)]
):
    return service.list_categories(session)


@router.post(
    "",
    response_model=CategoryRead,
    status_code=201,
    dependencies=[Depends(reject_query_parameters)],
    operation_id="API-CAT-02",
    summary="카테고리 등록·기존 이름 재사용",
    responses={
        200: {"model": CategoryRead, "description": "동일 이름의 기존 카테고리"},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_category(
    body: CategoryCreate,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
    response: Response,
):
    category, created = service.create_category(session, actor_id, body)
    response.status_code = 201 if created else 200
    return category


@router.patch(
    "/{category_id}",
    response_model=CategoryRead,
    dependencies=[Depends(reject_query_parameters)],
    operation_id="API-CAT-03",
    summary="카테고리 이름 수정",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "다른 카테고리의 이름과 중복"},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def rename_category(
    category_id: ResourceId,
    body: CategoryCreate,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
):
    return service.rename_category(session, actor_id, category_id, body)
