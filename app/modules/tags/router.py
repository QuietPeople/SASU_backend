from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorResponse
from app.db.session import get_db
from app.modules.tags import service
from app.modules.tags.schemas import TagCreate, TagListQuery, TagPage, TagRead

router = APIRouter(prefix="/tags", tags=["tags"])
ActorId = Annotated[int, Header(alias="X-Actor-Id", gt=0, le=9223372036854775807)]


@router.get(
    "",
    response_model=TagPage,
    operation_id="API-TAG-01",
    summary="태그 목록·이름 검색",
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def list_tags(
    query: Annotated[TagListQuery, Query()], session: Annotated[Session, Depends(get_db)]
):
    return service.list_tags(session, query)


@router.post(
    "",
    response_model=TagRead,
    status_code=201,
    operation_id="API-TAG-02",
    summary="태그 등록·기존 이름 재사용",
    responses={
        200: {"model": TagRead, "description": "동일 이름의 기존 태그"},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_tag(
    body: TagCreate,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
    response: Response,
):
    tag, created = service.create_tag(session, actor_id, body)
    response.status_code = 201 if created else 200
    return tag
