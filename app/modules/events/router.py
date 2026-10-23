from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    ActorId,
    Database,
    GenerationHeader,
    ResourceId,
    reject_query_parameters,
)
from app.core.exceptions import ErrorResponse
from app.modules.events import service
from app.modules.events.schemas import LearningEvent, LearningEventBody

router = APIRouter(
    prefix="/users/{user_id}/events",
    tags=["학습 이벤트"],
    dependencies=[Depends(reject_query_parameters)],
    responses={code: {"model": ErrorResponse} for code in (403, 404, 409, 422, 500)},
)


@router.post(
    "",
    status_code=201,
    response_model=LearningEvent,
    operation_id="API-EVT-01",
    summary="API-EVT-01 학습 이벤트 기록",
    responses={200: {"model": LearningEvent, "description": "동일 이벤트 재전송"}},
)
def record_event(
    user_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: LearningEventBody,
    response: Response,
) -> LearningEvent:
    result = service.record_event(session, actor_id, user_id, record_generation, body)
    response.status_code = 201 if result.recorded else 200
    return result
