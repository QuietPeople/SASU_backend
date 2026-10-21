from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.api.dependencies import ActorId, Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.modules.likes import service
from app.modules.likes.schemas import LikeState, RecordGeneration

GenerationHeader = Annotated[
    RecordGeneration,
    Header(
        alias="X-Record-Generation",
        description="현재 학습 기록 세대. 최초 0이며 DB learning_epoch보다 1 작습니다.",
    ),
]

router = APIRouter(
    prefix="/users/{user_id}/contents/{content_id}/like",
    tags=["좋아요"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        403: {"model": ErrorResponse, "description": "학습자 역할 필요"},
        404: {"model": ErrorResponse, "description": "사용자 또는 접근 가능한 콘텐츠 없음"},
        409: {"model": ErrorResponse, "description": "학습 기록 세대 불일치"},
        422: {"model": ErrorResponse, "description": "잘못된 ID·헤더·조회 조건"},
        500: {"model": ErrorResponse, "description": "저장 또는 조회 실패"},
    },
)


@router.put(
    "",
    response_model=LikeState,
    operation_id="API-LIK-01",
    summary="API-LIK-01 좋아요 등록",
    description=(
        "본인의 공개 콘텐츠 좋아요를 등록합니다. 반복 요청은 최초 등록 시각을 유지합니다. "
        "like_count는 DB 집계 뷰의 현재 값입니다. 요청 본문은 없습니다."
    ),
)
def like_content(
    user_id: ResourceId,
    content_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
) -> LikeState:
    return service.set_like(session, actor_id, user_id, content_id, record_generation, liked=True)


@router.delete(
    "",
    response_model=LikeState,
    operation_id="API-LIK-02",
    summary="API-LIK-02 좋아요 취소",
    description=(
        "본인의 좋아요를 취소합니다. 콘텐츠가 존재하면 비공개 상태에서도 취소할 수 있습니다. "
        "이미 취소했어도 200을 반환하며, 초기화 이전 세대의 요청은 409로 거절합니다."
    ),
)
def unlike_content(
    user_id: ResourceId,
    content_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
) -> LikeState:
    return service.set_like(session, actor_id, user_id, content_id, record_generation, liked=False)
