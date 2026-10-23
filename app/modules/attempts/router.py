"""파트 3의 ATM-01~03. 공통 라우터에서는 /api 아래 한 번 등록한다."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    ActorId,
    Database,
    GenerationHeader,
    ResourceId,
    reject_query_parameters,
)
from app.core.exceptions import ErrorResponse
from app.modules.attempts import service
from app.modules.attempts.schemas import Attempt, AttemptCreate, AttemptSubmission
from app.modules.responses.schemas import ResponseDetail

router = APIRouter(
    prefix="/users/{user_id}/question-attempts",
    tags=["퀴즈 풀이"],
    dependencies=[Depends(reject_query_parameters)],
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 409, 422, 500)},
)


@router.post(
    "",
    response_model=Attempt,
    status_code=201,
    operation_id="API-ATM-01",
    summary="API-ATM-01 새 퀴즈 풀이 시작",
    description=(
        "클라이언트 UUID로 버전을 고정합니다. 같은 입력 재전송은 원래 풀이를 반환합니다. "
        "노출 이벤트는 생성하지 않습니다."
    ),
    responses={200: {"model": Attempt, "description": "동일 풀이 재전송"}},
)
def create_attempt(
    user_id: ResourceId,
    request: AttemptCreate,
    response: Response,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
) -> Attempt:
    attempt, created = service.create_attempt(
        session, actor_id, user_id, record_generation, request
    )
    response.status_code = 201 if created else 200
    return attempt


@router.get(
    "/{attempt_id}",
    response_model=Attempt,
    operation_id="API-ATM-02",
    summary="API-ATM-02 풀이 상태·결과 복구",
    description=(
        "본인 현재 세대 풀이를 복구합니다. "
        "콘텐츠나 문항의 현재 공개·버전 상태가 바뀌어도 원래 결과를 제공합니다."
    ),
)
def recover_attempt(
    user_id: ResourceId,
    attempt_id: UUID,
    session: Database,
    actor_id: ActorId,
) -> Attempt:
    return service.recover_attempt(session, actor_id, user_id, attempt_id)


@router.put(
    "/{attempt_id}/response",
    response_model=ResponseDetail,
    operation_id="API-ATM-03",
    summary="API-ATM-03 답변·건너뛰기 제출",
    description=(
        "고정된 버전으로 채점하고 응답·오답 상태를 원자적으로 저장합니다. "
        "같은 답변 재전송은 기존 결과, 다른 답변은 409입니다. "
        "영상 퀴즈·피드 복습의 최초 제출에는 실제 QUIZ_DISPLAYED 이벤트가 필요합니다."
    ),
)
def submit_response(
    user_id: ResourceId,
    attempt_id: UUID,
    request: AttemptSubmission,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
) -> ResponseDetail:
    return service.submit_response(
        session, actor_id, user_id, attempt_id, record_generation, request
    )
