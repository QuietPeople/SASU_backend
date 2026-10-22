from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import ActorId, Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.modules.users.settings_router import GenerationHeader
from app.modules.watch_records import service
from app.modules.watch_records.schemas import WatchVisitBody, WatchVisitResult

router = APIRouter(
    prefix="/contents/{content_id}/watch-visits",
    tags=["시청 기록"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.put(
    "/{visit_id}",
    response_model=WatchVisitResult,
    operation_id="API-WCH-01",
    summary="API-WCH-01 시청 방문 보고",
    responses={
        403: {"model": ErrorResponse, "description": "학습자 역할 필요"},
        404: {"model": ErrorResponse, "description": "콘텐츠 없음"},
        409: {"model": ErrorResponse, "description": "학습 기록 세대 불일치"},
    },
)
def report_watch_visit(
    content_id: ResourceId,
    visit_id: UUID,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: WatchVisitBody,
) -> WatchVisitResult:
    return service.report_watch_visit(
        session, actor_id, content_id, visit_id, record_generation, body
    )
