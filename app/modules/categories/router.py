from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

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
ActorId = Annotated[int, Header(alias="X-Actor-Id", gt=0, le=9223372036854775807)]


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
