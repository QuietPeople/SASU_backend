from fastapi import APIRouter, Depends

from app.api.dependencies import (
    ActorId,
    Database,
    GenerationHeader,
    ResourceId,
    reject_query_parameters,
)
from app.core.exceptions import ErrorResponse
from app.modules.users import settings_service as service
from app.modules.users.settings_schemas import (
    FeedPosition,
    PatchSettingsBody,
    UpdateFeedPositionBody,
    UserSettings,
)

router = APIRouter(
    prefix="/users/{user_id}",
    tags=["사용자 설정"],
    dependencies=[Depends(reject_query_parameters)],
    responses={code: {"model": ErrorResponse} for code in (403, 404, 409, 422, 500)},
)


@router.get(
    "/settings",
    response_model=UserSettings,
    operation_id="API-USR-03",
    summary="API-USR-03 사용자 설정 조회",
)
def get_settings(user_id: ResourceId, session: Database, actor_id: ActorId) -> UserSettings:
    return service.get_settings(session, actor_id, user_id)


@router.patch(
    "/settings",
    response_model=UserSettings,
    operation_id="API-USR-04",
    summary="API-USR-04 사용자 설정 변경",
)
def patch_settings(
    user_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    body: PatchSettingsBody,
) -> UserSettings:
    return service.patch_settings(session, actor_id, user_id, body)


@router.get(
    "/feed-state",
    response_model=FeedPosition,
    operation_id="API-USR-05",
    summary="API-USR-05 마지막 피드 콘텐츠 조회",
)
def get_feed_position(user_id: ResourceId, session: Database, actor_id: ActorId) -> FeedPosition:
    return service.get_feed_position(session, actor_id, user_id)


@router.patch(
    "/feed-state",
    response_model=FeedPosition,
    operation_id="API-USR-06",
    summary="API-USR-06 마지막 피드 콘텐츠 반영",
)
def update_feed_position(
    user_id: ResourceId,
    session: Database,
    actor_id: ActorId,
    record_generation: GenerationHeader,
    body: UpdateFeedPositionBody,
) -> FeedPosition:
    return service.update_feed_position(session, actor_id, user_id, record_generation, body)
