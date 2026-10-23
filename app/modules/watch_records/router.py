from fastapi import APIRouter, Depends

from app.api.dependencies import (
    ActorId,
    Database,
    GenerationHeader,
    ResourceId,
    reject_query_parameters,
)
from app.core.exceptions import ErrorResponse
from app.modules.watch_records import service
from app.modules.watch_records.schemas import WatchVisitBody, WatchVisitResult

router = APIRouter(
    prefix="/users/{user_id}/contents/{content_id}",
    tags=["시청 기록"],
    dependencies=[Depends(reject_query_parameters)],
    responses={code: {"model": ErrorResponse} for code in (403, 404, 409, 422, 500)},
)


@router.post(
    "/watch-reports",
    response_model=WatchVisitResult,
    operation_id="API-WCH-01",
    summary="API-WCH-01 실제 시청 기록 반영",
)
def report_watch_visit(
    user_id: ResourceId,
    content_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: WatchVisitBody,
) -> WatchVisitResult:
    return service.report_watch_visit(
        session, actor_id, user_id, content_id, record_generation, body
    )
