"""본인 학습자와 관리자를 위한 제출 응답 상세 API."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.core.security import Actor, require_actor
from app.modules.responses import service
from app.modules.responses.schemas import ResponseDetail

router = APIRouter(
    prefix="/responses",
    tags=["응답"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        404: {"model": ErrorResponse, "description": "사용자 또는 접근 가능한 응답 없음"},
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.get(
    "/{response_id}",
    response_model=ResponseDetail,
    summary="API-RSP-01 응답 상세 조회",
)
def get_response(
    response_id: ResourceId,
    session: Database,
    actor: Annotated[Actor, Depends(require_actor)],
) -> ResponseDetail:
    return service.get_response(session, response_id, actor)
