"""공통 태그 검색과 관리자용 태그 등록 API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Database, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.core.security import require_admin
from app.modules.tags import service
from app.modules.tags.schemas import Tag, TagName, TagPage, TagQuery

router = APIRouter(
    prefix="/tags",
    tags=["태그"],
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.get("", response_model=TagPage, summary="API-TAG-01 태그 목록 조회")
def get_tags(query: Annotated[TagQuery, Query()], session: Database) -> TagPage:
    return service.get_tags(session, query)


@router.post(
    "",
    status_code=201,
    response_model=Tag,
    dependencies=[Depends(require_admin), Depends(reject_query_parameters)],
    summary="API-TAG-02 태그 등록·기존 태그 확인",
    responses={
        200: {"model": Tag, "description": "동일 이름 재사용"},
        400: {"model": ErrorResponse, "description": "JSON 구문 오류"},
        403: {"model": ErrorResponse, "description": "관리자 역할 필요"},
        404: {"model": ErrorResponse, "description": "사용자 없음"},
    },
)
def create_tag(request: TagName, response: Response, session: Database) -> Tag:
    tag, created = service.create_tag(session, request.name)
    response.status_code = 201 if created else 200
    return tag
