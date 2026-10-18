"""현재 퀴즈 공통 조회와 관리자 문항·해설 편집 API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.api.schemas import Page, PageQuery, ViewQuery
from app.core.exceptions import ErrorResponse
from app.core.security import Actor, require_actor, require_admin
from app.modules.questions import service
from app.modules.questions.schemas import (
    LearnerQuestion,
    QuestionInput,
    QuestionVersion,
    VersionInput,
    VersionSummary,
)

router = APIRouter(
    tags=["퀴즈·해설"],
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 409, 422, 500)},
)
Admin = [Depends(require_admin)]
NoQuery = [Depends(require_admin), Depends(reject_query_parameters)]


@router.get(
    "/contents/{content_id}/question",
    response_model=LearnerQuestion | None,
    summary="API-QST-01 현재 퀴즈 조회",
)
def current_question(
    content_id: ResourceId,
    query: Annotated[ViewQuery, Query()],
    actor: Annotated[Actor, Depends(require_actor)],
    session: Database,
):
    return service.get_current(session, content_id, query.view, actor)


@router.post(
    "/contents/{content_id}/question",
    status_code=201,
    response_model=QuestionVersion,
    dependencies=NoQuery,
    summary="API-QST-02 퀴즈 최초 등록",
)
def register_question(content_id: ResourceId, request: QuestionInput, session: Database):
    return service.register_question(session, content_id, request)


@router.post(
    "/questions/{question_id}/versions",
    status_code=201,
    response_model=QuestionVersion,
    dependencies=NoQuery,
    summary="API-QST-03 퀴즈 수정·새 버전 생성",
)
def revise_question(question_id: ResourceId, request: VersionInput, session: Database):
    return service.revise_question(session, question_id, request)


@router.get(
    "/questions/{question_id}/versions",
    response_model=Page[VersionSummary],
    dependencies=Admin,
    summary="API-QST-04 문항 버전 목록 조회",
)
def get_versions(question_id: ResourceId, query: Annotated[PageQuery, Query()], session: Database):
    return service.get_versions(session, question_id, query)


@router.get(
    "/questions/{question_id}/versions/{question_version_id}",
    response_model=QuestionVersion,
    dependencies=NoQuery,
    summary="API-QST-05 특정 문항 버전 상세 조회",
)
def get_version(question_id: ResourceId, question_version_id: ResourceId, session: Database):
    return service.get_version(session, question_id, question_version_id)
