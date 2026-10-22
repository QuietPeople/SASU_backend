"""통계·응답 목록. 기존 STA-04와 responses 상세 경로는 등록하지 않는다."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Database, ResourceId, reject_query_parameters
from app.api.schemas import Page, PageQuery
from app.core.exceptions import ErrorResponse
from app.core.security import require_admin
from app.modules.statistics import service
from app.modules.statistics.schemas import (
    ContentMetricItem,
    ContentStatistics,
    FlashcardStats,
    Overview,
    QuizStats,
    ResponseItem,
    ResponseQuery,
    VideoQuizStats,
    WrongReviewStats,
)

router = APIRouter(
    tags=["통계"],
    dependencies=[Depends(require_admin)],
    responses={code: {"model": ErrorResponse} for code in (403, 404, 422, 500)},
)
NoQuery = [Depends(reject_query_parameters)]


@router.get(
    "/statistics", response_model=Overview, dependencies=NoQuery, summary="API-STA-01 서비스 통계"
)
def overview(session: Database):
    return service.overview(session)


@router.get(
    "/statistics/contents",
    response_model=Page[ContentMetricItem],
    summary="API-STA-02 콘텐츠별 통계 목록",
)
def content_list(query: Annotated[PageQuery, Query()], session: Database):
    return service.content_list(session, query)


@router.get(
    "/contents/{content_id}/statistics",
    response_model=ContentStatistics,
    dependencies=NoQuery,
    summary="API-STA-03 콘텐츠 통계 전체",
)
def content_stats(content_id: ResourceId, session: Database):
    return service.content_stats(session, content_id)


@router.get(
    "/contents/{content_id}/statistics/quiz",
    response_model=VideoQuizStats,
    dependencies=NoQuery,
    summary="API-STA-05 영상 끝 퀴즈 통계",
)
def quiz(content_id: ResourceId, session: Database):
    return service.content_stats(session, content_id).quiz


@router.get(
    "/contents/{content_id}/statistics/feed-review",
    response_model=QuizStats,
    dependencies=NoQuery,
    summary="API-STA-06 피드 복습 통계",
)
def feed_review(content_id: ResourceId, session: Database):
    return service.content_stats(session, content_id).feed_review


@router.get(
    "/contents/{content_id}/statistics/wrong-answer-review",
    response_model=WrongReviewStats,
    dependencies=NoQuery,
    summary="API-STA-07 오답 복습 통계",
)
def wrong_review(content_id: ResourceId, session: Database):
    return service.content_stats(session, content_id).wrong_review


@router.get(
    "/contents/{content_id}/statistics/flashcards",
    response_model=FlashcardStats,
    dependencies=NoQuery,
    summary="API-STA-08 플래시카드 이용 통계",
)
def flashcards(content_id: ResourceId, session: Database):
    return service.content_stats(session, content_id).flashcards


@router.get("/responses", response_model=Page[ResponseItem], summary="API-STA-09 응답 이력 목록")
def responses(query: Annotated[ResponseQuery, Query()], session: Database):
    return service.responses(session, query)
