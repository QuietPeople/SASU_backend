from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from app.api.dependencies import ActorId, Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.modules.users import settings_service as service
from app.modules.users.settings_schemas import (
    FeedPosition,
    PatchSettingsBody,
    RecordGeneration,
    UpdateFeedPositionBody,
    UserSettings,
)

GenerationHeader = Annotated[
    RecordGeneration,
    Header(
        alias="X-Record-Generation",
        description="현재 학습 기록 세대. 최초 0이며 DB learning_epoch보다 1 작습니다.",
    ),
]

router = APIRouter(
    prefix="/users/{user_id}",
    tags=["사용자 설정"],
    dependencies=[Depends(reject_query_parameters)],
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 요청"},
        500: {"model": ErrorResponse, "description": "내부 처리 실패"},
    },
)


@router.get(
    "/settings",
    response_model=UserSettings,
    operation_id="API-USR-03",
    summary="API-USR-03 사용자 설정 조회",
    responses={
        404: {"model": ErrorResponse, "description": "사용자 없음"},
    },
)
def get_settings(user_id: ResourceId, session: Database, actor_id: ActorId) -> UserSettings:
    return service.get_settings(session, actor_id, user_id)


@router.patch(
    "/settings",
    response_model=UserSettings,
    operation_id="API-USR-04",
    summary="API-USR-04 사용자 설정 변경",
    responses={
        403: {"model": ErrorResponse, "description": "학습자 역할 필요"},
        404: {"model": ErrorResponse, "description": "사용자 없음"},
        409: {"model": ErrorResponse, "description": "학습 기록 세대 불일치"},
    },
)
def patch_settings(
    user_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: PatchSettingsBody,
) -> UserSettings:
    return service.patch_settings(session, actor_id, user_id, record_generation, body)


@router.get(
    "/feed-position",
    response_model=FeedPosition,
    operation_id="API-USR-05",
    summary="API-USR-05 마지막 피드 콘텐츠 조회",
    responses={
        404: {"model": ErrorResponse, "description": "사용자 없음"},
    },
)
def get_feed_position(
    user_id: ResourceId, session: Database, actor_id: ActorId
) -> FeedPosition:
    return service.get_feed_position(session, actor_id, user_id)


@router.put(
    "/feed-position",
    status_code=204,
    operation_id="API-USR-06",
    summary="API-USR-06 마지막 피드 콘텐츠 반영",
    responses={
        403: {"model": ErrorResponse, "description": "학습자 역할 필요"},
        404: {"model": ErrorResponse, "description": "사용자 또는 공개 콘텐츠 없음"},
        409: {"model": ErrorResponse, "description": "학습 기록 세대 불일치"},
    },
)
def update_feed_position(
    user_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: UpdateFeedPositionBody,
) -> None:
    service.update_feed_position(session, actor_id, user_id, record_generation, body)
