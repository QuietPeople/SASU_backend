"""관리자 학습 구조 관리와 공통 커리큘럼 조회 API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.api.schemas import Page
from app.core.exceptions import ErrorResponse
from app.core.security import Actor, require_actor, require_admin
from app.modules.curricula import service
from app.modules.curricula.schemas import (
    CurriculumDetail,
    CurriculumInput,
    CurriculumListQuery,
    CurriculumPatch,
    CurriculumProgress,
    CurriculumQuery,
    CurriculumSteps,
    CurriculumSummary,
    StepsInput,
)

router = APIRouter(
    tags=["커리큘럼"],
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 422, 500)},
)
CurrentActor = Annotated[Actor, Depends(require_actor)]
Writes = [Depends(require_admin), Depends(reject_query_parameters)]


@router.get(
    "/curriculums", response_model=Page[CurriculumSummary], summary="API-CRS-01 커리큘럼 목록 조회"
)
def get_list(
    query: Annotated[CurriculumListQuery, Query()], actor: CurrentActor, session: Database
):
    return service.get_list(session, query, actor)


@router.post(
    "/curriculums",
    status_code=201,
    response_model=CurriculumDetail,
    dependencies=Writes,
    summary="API-CRS-02 커리큘럼 생성",
)
def create_curriculum(request: CurriculumInput, actor: CurrentActor, session: Database):
    return service.create_curriculum(session, request, actor)


@router.get(
    "/curriculums/{curriculum_id}",
    response_model=CurriculumDetail,
    summary="API-CRS-03 커리큘럼 상세 조회",
)
def get_detail(
    curriculum_id: ResourceId,
    query: Annotated[CurriculumQuery, Query()],
    actor: CurrentActor,
    session: Database,
):
    return service.get_detail(session, curriculum_id, query, actor)


@router.patch(
    "/curriculums/{curriculum_id}",
    response_model=CurriculumSummary,
    dependencies=Writes,
    summary="API-CRS-04 커리큘럼 기본 정보 수정",
)
def patch_curriculum(
    curriculum_id: ResourceId, request: CurriculumPatch, actor: CurrentActor, session: Database
):
    return service.patch_curriculum(session, curriculum_id, request, actor)


@router.get(
    "/curriculums/{curriculum_id}/steps",
    response_model=CurriculumSteps,
    summary="API-CRS-05 커리큘럼 단계 조회",
)
def get_steps(
    curriculum_id: ResourceId,
    query: Annotated[CurriculumQuery, Query()],
    actor: CurrentActor,
    session: Database,
):
    detail = service.get_detail(session, curriculum_id, query, actor)
    return CurriculumSteps(items=detail.steps, total_steps=detail.summary.total_steps)


@router.put(
    "/curriculums/{curriculum_id}/steps",
    response_model=CurriculumSteps,
    dependencies=Writes,
    summary="API-CRS-06 커리큘럼 단계 전체 저장",
)
def save_steps(
    curriculum_id: ResourceId, request: StepsInput, actor: CurrentActor, session: Database
):
    return service.save_steps(session, curriculum_id, request, actor)


@router.get(
    "/users/{user_id}/curriculums/{curriculum_id}/progress",
    response_model=CurriculumProgress,
    dependencies=[Depends(reject_query_parameters)],
    summary="API-CRS-07 개인 커리큘럼 진행 조회",
)
def get_progress(
    user_id: ResourceId, curriculum_id: ResourceId, actor: CurrentActor, session: Database
):
    return service.get_progress(session, curriculum_id, user_id, actor)
