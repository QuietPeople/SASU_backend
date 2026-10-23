"""개인 현황 조회 라우터. 학습 기록 생성·수정은 하지 않는다."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.core.exceptions import ErrorResponse
from app.core.security import Actor, require_actor
from app.modules.dashboard import service
from app.modules.dashboard.schemas import CategoryDashboard, Dashboard

router = APIRouter(
    tags=["학습 현황"],
    dependencies=[Depends(reject_query_parameters)],
    responses={code: {"model": ErrorResponse} for code in (404, 422, 500)},
)
CurrentActor = Annotated[Actor, Depends(require_actor)]


@router.get(
    "/users/{user_id}/dashboard", response_model=Dashboard, summary="API-DSH-01 개인 학습 현황"
)
def summary(user_id: ResourceId, actor: CurrentActor, session: Database):
    return service.summary(session, user_id, actor)


@router.get(
    "/users/{user_id}/dashboard/categories",
    response_model=CategoryDashboard,
    summary="API-DSH-02 카테고리별 학습 현황",
)
def categories(user_id: ResourceId, actor: CurrentActor, session: Database):
    return service.categories(session, user_id, actor)
