"""원본 기록을 변경하지 않는 관리자 집계. 무표본 비율은 null."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.schemas import Page
from app.core.exceptions import ApiError
from app.modules.admin.schemas import Rate, ReactionStats
from app.modules.statistics import repository
from app.modules.statistics.schemas import (
    ContentStatistics,
    FlashcardStats,
    Overview,
    QuizStats,
    ResponseItem,
    ResponseQuery,
    VideoQuizStats,
    WrongReviewStats,
)


def rate(numerator: int, denominator: int) -> Rate:
    return Rate(
        numerator=numerator,
        denominator=denominator,
        percent=float(round(Decimal(numerator) * 100 / denominator, 2)) if denominator else None,
    )


def context_stats(rows, context: str) -> QuizStats:
    row = next((r for r in rows if r["context"] == context), {})
    counts = {
        key: row.get(key, 0)
        for key in (
            "displayed_count",
            "answered_count",
            "correct_count",
            "wrong_count",
            "skipped_count",
            "unanswered_display_count",
            "response_without_display_count",
        )
    }
    return QuizStats(
        context=context,
        **counts,
        accuracy=rate(counts["correct_count"], counts["answered_count"]),
        participation=rate(row.get("displayed_answered_count", 0), counts["displayed_count"]),
        skip_rate=rate(counts["skipped_count"], counts["answered_count"] + counts["skipped_count"]),
    )


def content_stats(session: Session, content_id: int) -> ContentStatistics:
    row = repository.content_stats(session, content_id)
    if row is None:
        raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠를 찾을 수 없습니다.")
    return ContentStatistics(
        content_id=content_id,
        reactions=ReactionStats(
            view_count=row["view_count"],
            like_count=row["like_count"],
            saved_count=row["saved_count"],
            watch_completion=rate(row["completed_count"], row["played_count"]),
        ),
        quiz=VideoQuizStats(
            **context_stats(row["contexts"], "VIDEO_END").model_dump(),
            first_accuracy=rate(row["first_correct"], row["first_answered"]),
        ),
        feed_review=context_stats(row["contexts"], "FEED_REVIEW"),
        wrong_review=WrongReviewStats(
            **context_stats(row["contexts"], "WRONG_REVIEW").model_dump(),
            current_unresolved_count=row["current_unresolved_count"],
            resolved_version_count=row["resolved_version_count"],
        ),
        flashcards=FlashcardStats(**{k: row[k] for k in FlashcardStats.model_fields}),
    )


def overview(session: Session) -> Overview:
    row = repository.overview(session)
    return Overview(
        **{
            k: row[k]
            for k in Overview.model_fields
            if k not in ("watch_completion", "first_quiz_accuracy")
        },
        watch_completion=rate(row["completed_count"], row["played_count"]),
        first_quiz_accuracy=rate(row["first_correct"], row["first_answered"]),
    )


def responses(session: Session, query: ResponseQuery) -> Page[ResponseItem]:
    row = repository.responses(session, query)
    return Page[ResponseItem](
        items=row["items"],
        total=row["total"],
        page=query.page,
        size=query.size,
        has_next=query.page * query.size < row["total"],
    )


def content_list(session: Session, query):
    from app.modules.statistics.schemas import ContentMetricItem

    row = repository.content_list(session, query.page, query.size)
    return Page[ContentMetricItem](
        items=row["items"],
        total=row["total"],
        page=query.page,
        size=query.size,
        has_next=query.page * query.size < row["total"],
    )
