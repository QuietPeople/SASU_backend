"""REV-01~04. POST 후보 조회도 학습 기록을 변경하지 않는 읽기 요청이다."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import ActorId, Database, ResourceId, reject_query_parameters
from app.api.schemas import Page
from app.core.exceptions import ErrorResponse
from app.modules.reviews import service
from app.modules.reviews.schemas import (
    CandidateFilter,
    Flashcard,
    FlashcardDetail,
    ReviewCandidate,
    ReviewListQuery,
    WrongAnswerItem,
    WrongAnswerQuery,
)

router = APIRouter(
    prefix="/users/{user_id}/reviews",
    tags=["복습·오답·플래시카드"],
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 422, 500)},
)


@router.post(
    "/feed/candidate",
    response_model=ReviewCandidate,
    operation_id="API-REV-01",
    summary="API-REV-01 피드 복습 후보 선정",
    dependencies=[Depends(reject_query_parameters)],
    description=(
        "시청 완료·현재 버전·기노출 및 재출제 조건으로 후보 1개를 조회합니다. "
        "풀이·노출은 생성하지 않습니다."
    ),
)
def get_candidate(
    user_id: ResourceId, request: CandidateFilter, session: Database, actor_id: ActorId
):
    return service.get_candidate(session, actor_id, user_id, request)


@router.get(
    "/wrong-answers",
    response_model=Page[WrongAnswerItem],
    operation_id="API-REV-02",
    summary="API-REV-02 현재 버전 오답 목록 조회",
)
def get_wrong_answers(
    user_id: ResourceId,
    query: Annotated[WrongAnswerQuery, Query()],
    session: Database,
    actor_id: ActorId,
):
    return service.get_wrong_answers(session, actor_id, user_id, query)


@router.get(
    "/flashcards",
    response_model=Page[Flashcard],
    operation_id="API-REV-03",
    summary="API-REV-03 플래시카드 앞면 목록 조회",
)
def get_flashcards(
    user_id: ResourceId,
    query: Annotated[ReviewListQuery, Query()],
    session: Database,
    actor_id: ActorId,
):
    return service.get_flashcards(session, actor_id, user_id, query)


@router.get(
    "/flashcards/{question_version_id}",
    response_model=FlashcardDetail,
    operation_id="API-REV-04",
    summary="API-REV-04 선택한 버전의 플래시카드 정답 조회",
    dependencies=[Depends(reject_query_parameters)],
)
def get_flashcard(
    user_id: ResourceId,
    question_version_id: ResourceId,
    session: Database,
    actor_id: ActorId,
):
    return service.get_flashcard(session, actor_id, user_id, question_version_id)
