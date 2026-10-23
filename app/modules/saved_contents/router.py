from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    ActorId,
    Database,
    GenerationHeader,
    ResourceId,
    reject_query_parameters,
)
from app.core.config import get_settings
from app.core.exceptions import ErrorResponse
from app.integrations.storage import LocalVideoStorage
from app.modules.saved_contents import service
from app.modules.saved_contents.schemas import (
    SavedContentsPage,
    SavedContentsQuery,
    SaveState,
)

router = APIRouter(
    prefix="/users/{user_id}",
    tags=["콘텐츠 저장"],
    responses={
        403: {"model": ErrorResponse, "description": "허용되지 않은 역할"},
        404: {"model": ErrorResponse, "description": "사용자·접근 가능한 콘텐츠·카테고리 없음"},
        409: {"model": ErrorResponse, "description": "학습 기록 세대 불일치"},
        422: {"model": ErrorResponse, "description": "잘못된 ID·헤더·조회 조건"},
        500: {"model": ErrorResponse, "description": "저장 또는 조회 실패"},
    },
)


@router.put(
    "/contents/{content_id}/saved",
    response_model=SaveState,
    operation_id="API-SAV-01",
    summary="API-SAV-01 콘텐츠 저장",
    description=(
        "본인의 공개 콘텐츠를 저장합니다. 반복 요청은 최초 저장 시각을 유지합니다. "
        "요청 본문은 없습니다."
    ),
    dependencies=[Depends(reject_query_parameters)],
)
def save_content(
    user_id: ResourceId,
    content_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
) -> SaveState:
    return service.set_saved(session, actor_id, user_id, content_id, record_generation, saved=True)


@router.delete(
    "/contents/{content_id}/saved",
    response_model=SaveState,
    operation_id="API-SAV-02",
    summary="API-SAV-02 콘텐츠 저장 해제",
    description=(
        "본인의 저장을 해제합니다. 콘텐츠가 존재하면 비공개 상태에서도 해제할 수 있습니다. "
        "이미 해제했어도 200을 반환하며 이전 세대의 요청은 409로 거절합니다."
    ),
    dependencies=[Depends(reject_query_parameters)],
)
def unsave_content(
    user_id: ResourceId,
    content_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
) -> SaveState:
    return service.set_saved(session, actor_id, user_id, content_id, record_generation, saved=False)


@router.get(
    "/saved-contents",
    response_model=SavedContentsPage,
    operation_id="API-SAV-03",
    summary="API-SAV-03 저장 콘텐츠 목록",
    description=(
        "본인 또는 관리자가 대상 학습자의 저장 목록을 조회합니다. 최신 저장순이며 "
        "비공개·재생 불가 콘텐츠는 제외합니다. 조회로 저장 관계를 삭제하지 않습니다."
    ),
)
def saved_contents(
    user_id: ResourceId,
    query: Annotated[SavedContentsQuery, Query()],
    session: Database,
    actor_id: ActorId,
) -> SavedContentsPage:
    return service.list_saved_contents(
        session, actor_id, user_id, query, LocalVideoStorage(get_settings().video_storage_root)
    )
