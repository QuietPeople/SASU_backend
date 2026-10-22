from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import Response

from app.api.dependencies import ActorId, Database, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.modules.events import service
from app.modules.events.schemas import LearningEventBody
from app.modules.users.settings_router import GenerationHeader

router = APIRouter(
    prefix="/events",
    tags=["학습 이벤트"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.put(
    "/{event_id}",
    status_code=204,
    operation_id="API-EVT-01",
    summary="API-EVT-01 학습 이벤트 보고",
    responses={
        403: {"model": ErrorResponse, "description": "학습자 역할 필요"},
        404: {"model": ErrorResponse, "description": "콘텐츠 없음"},
        409: {"model": ErrorResponse, "description": "학습 기록 세대 불일치"},
    },
)
def record_event(
    event_id: UUID,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: LearningEventBody,
) -> Response:
    service.record_event(session, actor_id, event_id, record_generation, body)
    return Response(status_code=204)
